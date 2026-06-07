import random
import cocotb

from tests.common import *


RNG_SEED = 0xD15A7C4


@cocotb.test()
async def test_random_kernel_sizes_complete_all(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    for i in range(50):
        await reset_dut(dut)

        num_blocks = random.randint(1, 20)
        completed = 0

        await launch_kernel(dut, num_blocks=num_blocks)

        while kernel_done(dut) == 0:
            active = core_mask(dut)
            assert active != 0, f"random kernel iter={i}: no active cores before done"

            # Random nonzero subset of active cores completes.
            sub = 0
            for c in range(NUM_CORES):
                if active & (1 << c):
                    if random.randint(0, 1):
                        sub |= (1 << c)

            if sub == 0:
                # Force at least one active completion.
                active_cores = [c for c in range(NUM_CORES) if active & (1 << c)]
                sub = 1 << random.choice(active_cores)

            completed += bin(sub).count("1")
            await pulse_block_done(dut, sub)

            assert completed <= num_blocks, (
                f"random kernel iter={i}: completed more than num_blocks"
            )

        assert completed == num_blocks, (
            f"random kernel iter={i}: expected completed {num_blocks}, got {completed}"
        )

        assert_dispatcher(
            dut,
            core_start=0,
            kernel_done=1,
            msg=f"random kernel complete iter={i}",
        )


@cocotb.test()
async def test_random_refill_block_indices_are_unique_and_ordered(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    for i in range(30):
        await reset_dut(dut)

        num_blocks = random.randint(5, 24)
        seen = set()

        await launch_kernel(dut, num_blocks=num_blocks)

        # Initial assigned blocks.
        for c in range(NUM_CORES):
            idx = get_block_idx(dut, c)
            if core_mask(dut) & (1 << c):
                seen.add(idx)

        while kernel_done(dut) == 0:
            active = core_mask(dut)

            active_cores = [c for c in range(NUM_CORES) if active & (1 << c)]
            done_core = random.choice(active_cores)
            await pulse_block_done(dut, 1 << done_core)

            # If core is still active after completion, it received a new block.
            if core_mask(dut) & (1 << done_core):
                idx = get_block_idx(dut, done_core)

                assert idx not in seen, (
                    f"iter={i}: duplicate blockIdx {idx}, seen={sorted(seen)}"
                )
                assert idx < num_blocks, (
                    f"iter={i}: blockIdx {idx} >= num_blocks {num_blocks}"
                )

                seen.add(idx)

        assert seen == set(range(num_blocks)), (
            f"iter={i}: expected all block IDs 0..{num_blocks-1}, got {sorted(seen)}"
        )


@cocotb.test()
async def test_random_inactive_done_noise_ignored(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    for i in range(30):
        await reset_dut(dut)

        num_blocks = random.randint(1, 4)
        await launch_kernel(dut, num_blocks=num_blocks)

        active = core_mask(dut)
        inactive = (~active) & 0xF

        if inactive:
            await pulse_block_done(dut, inactive)

            assert_dispatcher(
                dut,
                core_start=active,
                kernel_done=0,
                msg=f"inactive noise ignored iter={i}",
            )

        await pulse_block_done(dut, active)

        assert_dispatcher(
            dut,
            core_start=0,
            kernel_done=1,
            msg=f"inactive noise final iter={i}",
        )


@cocotb.test()
async def test_random_back_to_back_kernel_sizes(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    for i in range(30):
        num_blocks = random.randint(0, 12)

        await launch_kernel(dut, num_blocks=num_blocks)

        if num_blocks == 0:
            assert_dispatcher(
                dut,
                core_start=0,
                kernel_done=1,
                msg=f"random back-to-back empty iter={i}",
            )
            continue

        while kernel_done(dut) == 0:
            active = core_mask(dut)
            await pulse_block_done(dut, active)

        assert_dispatcher(
            dut,
            core_start=0,
            kernel_done=1,
            msg=f"random back-to-back complete iter={i}",
        )