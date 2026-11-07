# houji / XNU 12377 启动接口核对

日期：2026-11-08。范围为静态源码证据，不是实机验证。版本见 HOUJI-WORKLOG.md。

| 接口 | 当前源码证据 | 需要采取的动作 / 未验证项 |
| --- | --- | --- |
| NVRAM | 新 ArmDTPlatform 要求 /chosen 的 bank-size、proxy-data；旧 archive/scripts/make-houji-adt.py 也生成 8192 字节易失 CHRP bank | 不是从零补 NVRAM；验证该 bank 的结构是否符合新内核，确认最终使用的 ADT 含该属性 |
| GIC 路径 | 新 ArmCpu.cpp 查找 /arm-io/intc；旧生成器操作 /arm-io/gic | 显式转换节点名及属性，并校验，不把旧树直接交给新驱动 |
| GIC 数据布局 | 新驱动要求 ranges=3×uint64、reg=4×uint64、compatible 为带零结尾的 arm,gic-v3（11 字节） | ADT 是驱动直接 memcpy 的数据；不可直接复制 Linux FDT 的大端 cells |
| redistributor stride | 新驱动接受 0x20000/0x30000/0x40000；旧两核原型核对捕获 FDT 为 0x40000 | 0x40000 是候选来源值，不是本机已证实值 |
| PSCI | 新驱动读取 /psci/method，无默认 conduit；旧生成器仅两核分支加入 smc | 本机 FDT 核实 method，单核和多核配置分别验收 |
| CPU | 新驱动 reg 至少 4 字节，device_type 必须 cpu 加零；多核通过 sheng-smp 参数 opt-in | 名字虽为 sheng，不代表可直接使用其板级地址；初期不启用多核 |
| 内存 | houji UEFI MemoryMapLib.c 源自特定 xbl_config，包含固件和设备保留区 | 需要匹配本机固件/保留区；不能以 MemTotal 推导可分配物理范围 |
| framebuffer | 历史生成器硬编码 FC400000、1200×2670、stride 4800 | 未证明当前启动链保留此映射；须核对 GOP/引导交接，不能直接写屏 |
| 内存交接 | 历史生成器将 dram-base/size 置零，给 darwinboot-memory-size 指定分配窗口 | 需要跟踪 DarwinBoot 后续填充和分配成功路径，不能把零值视作实际物理布局 |
| 生成器来源 | archive/scripts/make-houji-adt.py 依赖 reference 提交 d68e05df683f863f054b0f9c063c54d2b1342b2a 的 tools/mkvermeeradt.py | 仓库规则明确 archive 仅历史参考；暂不运行，不将其包装成已可用入口 |

## 当前决定

先建立新 ADT 的明确输入契约与离线验证，复用有来源的硬件信息而不是整份历史树。
尚不生成可启动 ADT/boot.img，不新增硬件 MMIO 访问代码。
后续需获得本机 Linux 设备树作为硬件对照；它不直接等于 Apple ADT。

## 最小只读采集清单

1. ro.boot.hardware、ro.soc.model、ro.boot.bootloader，以及只读访问 /sys/firmware/fdt 的能力。
2. /sys/firmware/devicetree/base 的 cpus、memory、reserved-memory、PSCI、GIC 节点（优先原始 FDT）。
3. 确认是否存在 /dev/block/by-name/xbl_config_a、xbl_config_b；先只列路径，不读取整分区。
4. 原始树可能含设备标识，只留本机私有采集目录；公开报告只记录经过筛选的硬件参数。

采集权限不足时先记录，不通过 chmod、挂载或安装内核模块改变手机。
FDT 获取方案确认后再提供二进制导出命令，避免 Windows PowerShell 文本重定向破坏字节。
