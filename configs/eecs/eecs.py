import argparse
import os
import shlex

import m5
import m5.objects as mo
from m5.objects import NULL
from m5.util import addToPath

addToPath("../")
from common import (
    ObjectList,
    Simulation,
)


# List options
class ListBp(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        bp_list = ObjectList.ObjectList(
            getattr(m5.objects, "BranchPredictor", None)
        )
        cbp_list = ObjectList.ObjectList(
            getattr(m5.objects, "ConditionalPredictor", None)
        )
        bp_list.print()
        cbp_list.print()
        mo.sys.exit(0)


class ListPrefetcher(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        ObjectList.hwp_list.print()
        mo.sys.exit(0)


# helpers


def get_processes(args):
    """Interprets provided args and returns a list of processes"""

    multiprocesses = []
    inputs = []
    outputs = []
    errouts = []
    pargs = []

    workloads = args.cmd.split(";")
    for w in workloads:
        if not os.path.exists(w):
            fatal(f"Binary of workload not found: {w}")

    if args.input != "":
        inputs = args.input.split(";")
    if args.output != "":
        outputs = args.output.split(";")
    if args.errout != "":
        errouts = args.errout.split(";")
    if args.options != "":
        pargs = args.options.split(";")

    idx = 0
    for wrkld in workloads:
        process = mo.Process(pid=100 + idx)
        process.executable = wrkld
        process.cwd = os.getcwd()
        process.gid = os.getgid()

        if args.env:
            with open(args.env) as f:
                process.env = [line.rstrip() for line in f]

        if len(pargs) > idx:
            process.cmd = [wrkld] + pargs[idx].split()
        else:
            process.cmd = [wrkld]

        if len(inputs) > idx:
            process.input = inputs[idx]
        if len(outputs) > idx:
            process.output = outputs[idx]
        if len(errouts) > idx:
            process.errout = errouts[idx]

        multiprocesses.append(process)
        idx += 1

    return multiprocesses


def fatal(msg: str):
    raise RuntimeError(msg)


def set_if_hasattr(obj, name, value):
    if hasattr(obj, name):
        setattr(obj, name, value)


def instantiate_by_name(module, class_name: str, default_none: bool = False):
    if class_name is None:
        return None
    if class_name.lower() == "none":
        return None

    cls = getattr(module, class_name, None)
    if cls is None:
        names = sorted(
            [
                n
                for n in dir(module)
                if n.endswith("Prefetcher")
                or n.endswith("BP")
                or n == "BranchPredictor"
            ]
        )
        fatal(
            f"Unknown class '{class_name}'. Candidates include: {', '.join(names)}"
        )
    return cls()


def make_prefetcher(name: str):
    if name.lower() == "none":
        return NULL
    bp = instantiate_by_name(mo, name, default_none=True)
    return bp if bp is not None else NULL


def make_bp(name: str):
    bp_list = ObjectList.ObjectList(
        getattr(m5.objects, "BranchPredictor", None)
    ).get_names()
    cbp_list = ObjectList.ObjectList(
        getattr(m5.objects, "ConditionalPredictor", None)
    ).get_names()

    if name.lower() == "none":
        return NULL
    elif name in bp_list:
        bp = instantiate_by_name(mo, name, default_none=True)
    elif name == "StaticBP":
        bp = instantiate_by_name(mo, "BranchPredictor", default_none=True)
        bp.conditionalBranchPred = instantiate_by_name(
            mo, name, default_none=True
        )
        bp.indirectBranchPred = instantiate_by_name(
            mo, "StaticIndirectBP", default_none=True
        )
    elif name in cbp_list:
        bp = instantiate_by_name(mo, "BranchPredictor", default_none=True)
        bp.conditionalBranchPred = instantiate_by_name(
            mo, name, default_none=True
        )
    else:
        fatal(f"Unknown BP.")

    return bp if bp is not None else NULL


# Cache


class L1ICache(mo.Cache):
    tag_latency = 1
    # タグアレイアクセスのレイテンシ
    data_latency = 1
    # データアレイアクセスのレイテンシ
    response_latency = 1
    # キャッシュが応答するまでのレイテンシ
    mshrs = 8
    # Miss Status Holding Registers: キャッシュミス時のリクエスト（アドレスやデータ）を保持しておくレジスタの数
    tgts_per_mshr = 20
    # Targets per MSHR: MSHRが保持できるリクエストの数
    writeback_clean = True
    #
    is_read_only = True
    # 読み取り専用
    sequential_access = False

    def __init__(self, size, assoc, prefetcher=NULL):
        super().__init__()
        self.size = size
        self.assoc = assoc
        if prefetcher != NULL:
            self.prefetcher = prefetcher

    def connect_cpu(self, cpu):
        self.cpu_side = cpu.icache_port

    def connect_bus(self, bus):
        self.mem_side = bus.cpu_side_ports


class L1DCache(mo.Cache):
    tag_latency = 1
    data_latency = 1
    response_latency = 1
    mshrs = 8
    tgts_per_mshr = 20
    write_buffers = 8
    sequential_access = False

    def __init__(self, size, assoc, prefetcher=NULL):
        super().__init__()
        self.size = size
        self.assoc = assoc
        if prefetcher != NULL:
            self.prefetcher = prefetcher

    def connect_cpu(self, cpu):
        self.cpu_side = cpu.dcache_port

    def connect_bus(self, bus):
        self.mem_side = bus.cpu_side_ports


class L2Cache(mo.Cache):
    response_latency = 1
    mshrs = 32
    tgts_per_mshr = 20
    write_buffers = 8
    sequential_access = False

    def __init__(self, size, assoc, latency, prefetcher=NULL):
        super().__init__()
        self.size = size
        self.assoc = assoc
        self.tag_latency = latency
        self.data_latency = latency
        if prefetcher != NULL:
            self.prefetcher = prefetcher

    def connect_cpu_side_bus(self, cpu):
        self.cpu_side = cpu.mem_side_ports

    def connect_mem_side_bus(self, bus):
        self.mem_side = bus.cpu_side_ports


# CPU


def create_cpu(cpu_type: str, cpu_id: int):
    t = cpu_type.lower()
    if t == "o3":
        return mo.RiscvO3CPU(cpu_id=cpu_id)
    if t == "minor":
        return mo.RiscvMinorCPU(cpu_id=cpu_id)
    fatal(f"Unsupported --cpu-type '{cpu_type}'. Supported: [o3, minor]")


def apply_bp(cpu, bp_name: str):
    bp = make_bp(bp_name)
    if bp != NULL and hasattr(cpu, "branchPred"):
        cpu.branchPred = bp


def apply_width(cpu, cpu_type: str, width: int):
    if width < 0:
        fatal("--superscalar must be >= 0.")

    t = cpu_type.lower()
    if width == 0:
        if t == "o3":
            w = 4
        else:
            w = 1
    else:
        w = width

    if t == "o3":
        for attr in [
            "fetchWidth",
            "decodeWidth",
            "renameWidth",
            "dispatchWidth",
            "issueWidth",
            "wbWidth",
            "commitWidth",
            "squashWidth",
        ]:
            set_if_hasattr(cpu, attr, w)
    elif t == "minor":
        for attr in [
            "decodeInputWidth",
            "executeInputWidth",
            "executeIssueLimit",
            "executeCommitLimit",
        ]:
            set_if_hasattr(cpu, attr, w)


# main


def parse_args():
    p = argparse.ArgumentParser("eecs.py")

    p.add_argument(
        "--cmd",
        required=True,
        help="Path to the RISC-V binary of workload to run.",
    )
    p.add_argument(
        "--options",
        default="",
        help="Command-line arguments for the workload.",
    )

    p.add_argument(
        "--cpu-type",
        choices=["o3", "minor"],
        default="o3",
        help="Type of CPU.\n    o3   : Out-of-order model\n    minor: In-order model",
    )
    p.add_argument("--num-cpus", type=int, default=1, help="Number of CPUs.")
    p.add_argument(
        "--cpu-clock", default="2GHz", help="Clock frequency of CPU."
    )
    p.add_argument(
        "--superscalar",
        type=int,
        default=0,
        help="Superscalar width. Defautls to 0, which represent 1 in MinorCPU and 4 in O3CPU.",
    )

    p.add_argument(
        "--l1i-size", default="32KiB", help="Size of L1 instruction cache."
    )
    p.add_argument(
        "--l1d-size", default="32KiB", help="Size of L1 data cache."
    )
    p.add_argument("--l2-size", default="256KiB", help="Size of L2 cache.")

    p.add_argument(
        "--l1i-assoc",
        type=int,
        default=4,
        help="Associativity of L1 instruction cache.",
    )
    p.add_argument(
        "--l1d-assoc",
        type=int,
        default=4,
        help="Associativity of L1 data cache.",
    )
    p.add_argument(
        "--l2-assoc",
        type=int,
        default=8,
        help="Associativity of L2 instruction cache.",
    )

    p.add_argument(
        "--l2-latency-cycles",
        type=int,
        default=10,
        help="Latency of L2 cache in cycles",
    )

    p.add_argument(
        "--l1i-prefetcher",
        default="none",
        help="Type of hardware prefetcher for L1 instruction cache.",
    )
    p.add_argument(
        "--l1d-prefetcher",
        default="none",
        help="Type of hardware prefetcher for L1 data cache.",
    )
    p.add_argument(
        "--l2-prefetcher",
        default="none",
        help="Type of ardware prefetcher for L2 cache.",
    )

    p.add_argument("--bp", default="LocalBP", help="Type of branch predictor.")

    p.add_argument("--mem-size", default="2GiB", help="Size of main memory.")

    p.add_argument(
        "--sys-clock",
        default=None,
        help="Optional system clock. Defaults to --cpu-clock.",
    )

    p.add_argument(
        "--cacheline-size",
        type=int,
        default=64,
        help="Size of cache line in byte.",
    )

    p.add_argument(
        "--list-bp",
        action=ListBp,
        nargs=0,
        help="List available branch predictors.",
    )
    p.add_argument(
        "--list-prefetcher",
        action=ListPrefetcher,
        nargs=0,
        help="List available hardware prefetchers.",
    )

    p.add_argument("-i", "--input", default="", help="Read stdin from a file.")
    p.add_argument("--output", default="", help="Redirect stdout to a file.")
    p.add_argument("--errout", default="", help="Redirect stderr to a file.")
    p.add_argument(
        "-e",
        "--env",
        default="",
        help="Initialize workload environment from text file.",
    )

    return p.parse_args()


def main():
    args = parse_args()

    multiprocesses = []
    multiprocesses = get_processes(args)
    mp0_path = multiprocesses[0].executable

    # system
    system = mo.System()
    system.clk_domain = mo.SrcClockDomain()
    system.clk_domain.clock = args.sys_clock or args.cpu_clock
    system.clk_domain.voltage_domain = mo.VoltageDomain()

    system.mem_mode = "timing"
    system.mem_ranges = [mo.AddrRange(args.mem_size)]
    system.cache_line_size = args.cacheline_size

    # Shared memory bus and L2 bus
    system.membus = mo.SystemXBar()
    system.l2bus = mo.L2XBar()
    system.system_port = system.membus.cpu_side_ports

    # Shared L2
    system.l2cache = L2Cache(
        size=args.l2_size,
        assoc=args.l2_assoc,
        latency=args.l2_latency_cycles,
        prefetcher=make_prefetcher(args.l2_prefetcher),
    )
    system.l2cache.connect_cpu_side_bus(system.l2bus)
    system.l2cache.connect_mem_side_bus(system.membus)

    # Memory controller
    system.mem_ctrl = mo.MemCtrl()
    system.mem_ctrl.dram = mo.DDR3_1600_8x8()
    system.mem_ctrl.dram.range = system.mem_ranges[0]
    system.mem_ctrl.port = system.membus.mem_side_ports

    # CPUs
    system.cpu = [create_cpu(args.cpu_type, i) for i in range(args.num_cpus)]

    for i, cpu in enumerate(system.cpu):
        # Per-core clock domain if you want it explicit
        cpu.clk_domain = mo.SrcClockDomain()
        cpu.clk_domain.clock = args.cpu_clock
        cpu.clk_domain.voltage_domain = system.clk_domain.voltage_domain

        apply_bp(cpu, args.bp)
        apply_width(cpu, args.cpu_type, args.superscalar)

        # Private L1s
        ic = L1ICache(
            size=args.l1i_size,
            assoc=args.l1i_assoc,
            prefetcher=make_prefetcher(args.l1i_prefetcher),
        )
        dc = L1DCache(
            size=args.l1d_size,
            assoc=args.l1d_assoc,
            prefetcher=make_prefetcher(args.l1d_prefetcher),
        )

        setattr(system, f"cpu{i}_icache", ic)
        setattr(system, f"cpu{i}_dcache", dc)

        ic.connect_cpu(cpu)
        dc.connect_cpu(cpu)
        ic.connect_bus(system.l2bus)
        dc.connect_bus(system.l2bus)

        # Page-table walkers, if exposed by this CPU/MMU model.
        if hasattr(cpu, "mmu"):
            try:
                cpu.mmu.connectWalkerPorts(
                    system.l2bus.cpu_side_ports,
                    system.l2bus.cpu_side_ports,
                )
            except Exception:
                pass

        cpu.createInterruptController()

        # SE workload: one process object per core

        if len(multiprocesses) == 1:
            cpu.workload = multiprocesses[0]
        else:
            cpu.workload = multiprocesses[i]
        cpu.createThreads()

    system.workload = mo.SEWorkload.init_compatible(mp0_path)

    root = mo.Root(full_system=False, system=system)
    m5.instantiate()

    print("Starting simulation")
    print(f"  cmd               : {[p.cmd for p in multiprocesses]}")
    print(f"  cpu_type          : {args.cpu_type}")
    print(f"  num_cpus          : {args.num_cpus}")
    print(f"  cpu_clock         : {args.cpu_clock}")
    print(f"  bp                : {args.bp}")
    print(
        f"  superscalar       : {args.superscalar if args.superscalar != 0 else 4 if args.cpu_type.lower() == "o3" else 1}"
    )
    print(
        f"  L1I               : {args.l1i_size}, assoc={args.l1i_assoc}, pref={args.l1i_prefetcher}"
    )
    print(
        f"  L1D               : {args.l1d_size}, assoc={args.l1d_assoc}, pref={args.l1d_prefetcher}"
    )
    print(
        f"  L2                : {args.l2_size}, assoc={args.l2_assoc}, pref={args.l2_prefetcher}"
    )

    exit_event = m5.simulate()
    print(f"Exiting @ tick {m5.curTick()} because {exit_event.getCause()}")


if __name__ == "__m5_main__":
    main()
