import random
import cocotb

from tests.common import *


RNG_SEED = 0x574C4


def rand_u32():
    return random.getrandbits(32)


@cocotb.test()
async def test_random_push_pop_sequence_against_model(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    model = []

    for i in range(200):
        can_push = len(model) < STACK_DEPTH
        can_pop = len(model) > 0

        if can_push and can_pop:
            op = random.choice(["push", "pop"])
        elif can_push:
            op = "push"
        else:
            op = "pop"

        if op == "push":
            pc = rand_u32()
            await push_entry(dut, pc)
            model.append(u32(pc))
        else:
            await pop_entry(dut)
            model.pop()

        assert_against_model(dut, model, msg=f"random push/pop iter={i}")


@cocotb.test()
async def test_random_overflow_attempts_do_not_change_stack(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    model = []

    for idx in range(STACK_DEPTH):
        pc = rand_u32()
        await push_entry(dut, pc)
        model.append(u32(pc))

    assert_against_model(dut, model, msg="pre-overflow full stack")
    assert_stack(dut, full=1, msg="pre-overflow full flag")

    for i in range(50):
        old_model = list(model)

        dut.push.value = 1
        dut.pop.value = 0
        dut.push_return_pc.value = rand_u32()
        await Timer(1, unit="ns")

        assert_stack(dut, overflow=1, msg=f"random overflow combinational iter={i}")

        await step(dut)
        dut.push.value = 0
        await Timer(1, unit="ns")

        model = old_model

        assert_against_model(dut, model, msg=f"random overflow ignored iter={i}")
        assert_stack(dut, full=1, overflow=0, msg=f"random overflow flags iter={i}")


@cocotb.test()
async def test_random_pop_empty_does_not_change_outputs(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    for i in range(50):
        await pop_entry(dut)

        assert_stack(
            dut,
            empty=1,
            full=0,
            overflow=0,
            top_pc=0,
            msg=f"random pop empty iter={i}",
        )


@cocotb.test()
async def test_random_reset_mid_sequence(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    model = []

    for i in range(50):
        for _ in range(random.randint(1, STACK_DEPTH)):
            if len(model) < STACK_DEPTH:
                pc = rand_u32()
                await push_entry(dut, pc)
                model.append(u32(pc))

        assert_against_model(dut, model, msg=f"before random reset iter={i}")

        dut.rst.value = 1
        await step(dut)
        dut.rst.value = 0
        await Timer(1, unit="ns")

        model.clear()

        assert_against_model(dut, model, msg=f"after random reset iter={i}")


@cocotb.test()
async def test_random_fill_and_drain_lifo(dut):
    random.seed(RNG_SEED + 4)
    await setup_dut(dut)

    for trial in range(50):
        model = []

        for depth in range(STACK_DEPTH):
            pc = rand_u32()
            await push_entry(dut, pc)
            model.append(u32(pc))

            assert_against_model(dut, model, msg=f"fill trial={trial} depth={depth}")

        assert_stack(dut, full=1, msg=f"full trial={trial}")

        for depth in range(STACK_DEPTH):
            await pop_entry(dut)
            model.pop()

            assert_against_model(dut, model, msg=f"drain trial={trial} depth={depth}")


@cocotb.test()
async def test_random_simultaneous_push_pop_against_model(dut):
    # Independently randomize push and pop each cycle (so ~25% of cycles
    # assert both), fuzzing call_stack.sv's real "pop wins whenever legal"
    # simultaneous-assert behavior against model_step(). Also checks the
    # combinational overflow flag pre-edge on every iteration, since that's
    # the one signal that must react before any clock edge at all.
    random.seed(RNG_SEED + 5)
    await setup_dut(dut)

    model = []

    for i in range(300):
        push = random.random() < 0.5
        pop = random.random() < 0.5
        pc = rand_u32()
        pre_full = len(model) == STACK_DEPTH

        dut.push.value = 1 if push else 0
        dut.pop.value = 1 if pop else 0
        dut.push_return_pc.value = u32(pc)
        await Timer(1, unit="ns")

        expected_overflow = 1 if (push and pre_full) else 0
        assert_stack(
            dut,
            overflow=expected_overflow,
            msg=f"pre-edge combinational overflow iter={i} push={push} pop={pop}",
        )

        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        dut.push.value = 0
        dut.pop.value = 0
        await Timer(1, unit="ns")

        model_step(model, push, pop, pc)

        assert_against_model(
            dut, model, msg=f"post-edge iter={i} push={push} pop={pop}"
        )
