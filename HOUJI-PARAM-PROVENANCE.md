# houji 启动参数来源表（P1 结项）

日期：2026-11-08。范围为静态源码与本机 FDT 的离线对照，**不是实机验证**，不产出可启动配置。

## 证据来源

| 编号 | 证据 | 标识 |
| --- | --- | --- |
| E1 | 本机原始 FDT（只读采集，仓库外） | 961025 字节，SHA256 `447f252737e719c110495b0b9100d2aac8783265a862f35dd6ae80f820f22ddd` |
| E2 | `drivers/ArmDTPlatform/ArmDTPlatform.cpp` | none24smu/UniXNU `68c5134` |
| E3 | `drivers/ArmCpu/ArmCpu.cpp` | 同上 |
| E4 | Apple XNU `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`（12377.121.6） | IONVRAM / IONVRAMCHRPHandler / machine_routines |
| E5 | `uefi/overlay/.../Library/MemoryMapLib/MemoryMapLib.c` | UniXNU-houji `99beb10`，注释标注源自 xbl_config 捕获 |
| E6 | `archive/scripts/make-houji-adt.py` | 同上，仓库规则标注为历史参考 |

状态定义：**已证实**＝有直接字节级或源码级证据；**候选**＝有来源但与运行期行为尚未对齐；**阻塞**＝无证据，且已明确缺什么。

## 一、平台入口（E2 `configure`）

`configure` 要求 `/cpus`、`/arm-io`、`/defaults`、`/options` **四个节点同时存在**，缺一即返回 false。

| 参数 | 消费方要求 | 来源证据 | 取值 | 状态 |
| --- | --- | --- | --- | --- |
| `/cpus` | 节点存在 | E1 `/cpus` | 存在 | 已证实 |
| `/arm-io` | 节点存在，且 `createDeviceNubs` 遍历其**全部**子节点 | E1 对应节点为 `/soc` | 需重命名 | 候选 |
| `/defaults` | 节点存在 | E1 无此节点（Apple 专有） | 需合成 | 阻塞 |
| `/options` | 节点存在 | E1 无此节点（Apple 专有） | 需合成 | 阻塞 |
| `/chosen` `nvram-bank-size` | 长度恰为 4 字节 | E1 `/chosen` 只有 initrd/kaslr/bootargs/stdout-path | 8192（来自 E6 历史 fixture） | 候选 |
| `/chosen` `nvram-proxy-data` | 非零长度，且长度须等于 bank-size | E1 无 | 8192 字节空白 v1 CHRP（已过 `check-houji-chrp.py` 模型校验） | 候选 |

`/defaults` 与 `/options` 属 Apple ADT 专有节点，Linux FDT 中不存在，必须由生成器合成。`PE_parse_boot_argn` 的实参来自 DarwinBoot 填充的 BootArgs，不依赖 `/options` 内容；`/options` 仅需存在。

## 二、GIC（E3 `mapGic`，行 196–235）

| 参数 | 消费方要求 | E1 原始形态 | 目标编码 | 状态 |
| --- | --- | --- | --- | --- |
| `/arm-io` `ranges` | 长度**恰好 24 字节**（3×LE u64） | `/soc` ranges 为 **16 字节**（4 cell） | `0, 0, 0xFFFFFFFF` | 候选 |
| `/arm-io/intc` `reg` | 长度**恰好 32 字节**（4×LE u64） | 16 字节（4×BE u32） | `0x17100000, 0x10000, 0x17180000, 0x200000` | 已证实（数值） |
| `/arm-io/intc` `compatible` | 长度**恰好 11 字节**，含结尾 NUL | `arm,gic-v3` | 同 | 已证实 |
| `/arm-io/intc` `redistributor-stride` | 长度 8 字节；只接受 `0x20000/0x30000/0x40000` | 8 字节 BE = `0x40000` | `0x40000` LE | 已证实 |
| 节点名 `intc` | `fromPath("/arm-io/intc")` 硬编码 | `interrupt-controller@17100000` | 需改名 | 候选 |

驱动另有硬性下限：`regions[1] ≥ 0x10000`、`regions[3] ≥ 0x20000`，且两个区域须落在 `[bus[0], bus[0]+bus[2]]` 内。候选值满足全部条件（`0x10000 ≥ 0x10000`、`0x200000 ≥ 0x20000`、`0x17100000 ≤ 0xFFFFFFFF`）。该判断只验证编码与边界，**不验证 MMIO 可访问性**。

**ranges 解析陷阱（本轮新发现）**：`/soc` 声明 `#address-cells=1`、`#size-cells=1`，但父节点 `/` 声明 `#address-cells=2`。按 DT 规范，ranges 条目为「子地址(#addr-cells) + 父地址(父#addr-cells) + 长度(#size-cells)」= 1+2+1 = **4 cell = 16 字节**，与实测一致。若按 3 cell 解析会错位。这是 24 字节目标值必须重新编码、不可直接拷贝的根本原因。

## 三、CPU 与拓扑（E3 `probe`，E4 `machine_routines.c`）

| 参数 | 消费方要求 | E1 原始形态 | 目标编码 | 状态 |
| --- | --- | --- | --- | --- |
| `device_type` | 长度 4 且为 `cpu` | `cpu\0` | 同 | 已证实 |
| `reg` | ≥4 字节；须保留 affinity 供 `ml_get_cpu_number` 与 PSCI CPU_ON 使用 | 8 字节 BE：`0x0,0x100,…,0x700` | LE u32 同值 | 已证实（数值） |
| `state` | `ml_is_boot_cpu` 必须读到，缺失即 panic；`running` 视为启动核 | **E1 无 state 属性** | 需合成 | 阻塞 |
| 唯一 running CPU | 必须有且仅有一个被接受的 running CPU | 无法从 FDT 推断 | — | 阻塞 |
| `/cpus` 直接子节点 | 遍历全部直接子节点，按接受顺序生成逻辑 ID | 8 个 `cpu@N` **加一个 `cpu-map`** | 必须剔除 `cpu-map` | 已证实风险（现有生成器已按 `device_type` 过滤，风险在整体转换路径） |
| `cluster-type` | 缺省进入 SMP 分类；E/M/P 改变分类 | E1 无 | 不设置 | 候选 |

`cpu-map` 是 Linux 专用拓扑描述节点，若不剔除会被当作 CPU 节点参与逻辑 ID 生成。本机 FDT 确实存在该节点，必须在生成 ADT 时显式过滤，不能依赖命名猜测。

## 四、PSCI（E3 `psciConduit`，行 464–478）

| 参数 | 消费方要求 | E1 原始形态 | 目标 | 状态 |
| --- | --- | --- | --- | --- |
| `/psci` 路径 | `fromPath("/psci")` 硬编码 | 实际在 `/soc/psci` | 需上提至根 | 候选 |
| `method` | 长度恰为 4 字节，`smc\0` 或 `hvc\0` | `smc\0`（4 字节） | `smc\0` | 已证实 |

驱动无默认 conduit，读不到即失败。本机为 `smc`，与历史假设一致。

## 五、内存与交接（E5，E1 `/memory`）

| 参数 | 证据 | 状态 |
| --- | --- | --- |
| DRAM 总量 | E1 `/memory/ddr_size = 0x10`（16 GiB）；16 个 reg 元组非零合计 15.15 GiB | 已证实 |
| `/memory/reg` 形态 | 16 个元组，含 1 个零长度项；最大两块 `0x8C0000000+0x140000000`(5 GiB) 与 `0xA00000000+0x200000000`(8 GiB) 相邻 | 已证实 |
| dram-base / dram-size 属性 | E4 在 `pe_init.c`、`arm_vm_init.c` 未发现字符串；DarwinBoot 不重写 ADT 该字段 | 阻塞（完整消费链未定） |
| 分配窗口 | DarwinBoot 仅从 `EfiConventionalMemory` 分配，默认 256 MiB，显式值 256 MiB–8 GiB 且 2 MiB 对齐 | 候选 |
| high-RAM 窗口 | 历史窗口 `[0x8C0000000,0xBEA400000)` 落在上述两块并集内，仅为范围覆盖 | 候选，不可视为可分配 |

## 六、显示与引导交接

| 参数 | 证据 | 状态 |
| --- | --- | --- |
| splash 保留区 | E1 `splash_region` = `0xFC400000 + 0x2B00000`，与 E5 `Display_Reserved` 同址同长 | 已证实 |
| framebuffer 几何 | E6 硬编码 `1200×2670`、stride `4800`；E1 只给出保留区，不含几何 | 阻塞 |
| GOP 交接 | `ReadBootVideo` 在分配前执行，失败即终止；无采集证据 | 阻塞 |
| EL1 | Boot 要求 `CurrentEL` 原始值 4 | 阻塞（需运行期读取） |

## 七、三个未决项的本轮结论

### 1. XBL_Ramdump 命名与地址错位 —— 已定论

E5 中 `{"XBL_Ramdump", 0x84800000, 0x00200000}` 的**范围正确、名称错误**。E1 精确证据：

- `qlink_logging_region@84800000` = `0x84800000 + 0x200000`
- `xbl_ramdump_region@84a00000` = `0x84A00000 + 0x200000`

该条目的地址与长度与 qlink_logging 完全一致，与 xbl_ramdump 不一致。结论：应更名为 `QLINK_Logging`；真正的 xbl_ramdump 区（`0x84A00000`，2 MiB）在 E5 中没有对应条目。

是否需要补条目取决于固件自身提供的 EFI 内存图是否已保留该区，本轮未读取运行期内存图，因此**不判定为缺陷**，标记为待验证。风险方向明确：若该区在 UEFI 阶段被判为 conventional，DarwinBoot 的窗口分配可能落入其中。

### 2. ramoops 与 FD 区重叠 —— 生命周期交接，但存在实际代价

E1 `ramoops_region` = `0xA7000000 + 0x400000`，且是**唯一**覆盖该范围的保留节点；属性含 `console-size=0x200000`、`pmsg-size=0x200000`（合计正好 4 MiB），无 `no-map`。

E5 在同一地址布置 `FD_Reserved`(`0xA7000000`,1 MiB) + `UEFI_FD`(`0xA7100000`,3 MiB)，合计恰好 4 MiB，与 ramoops 完全重合。

结论：这不是地址冲突，而是**同一 4 MiB 的所有权在两阶段间转换**——UEFI 阶段放固件卷，交接后由内核复用为 pstore。实际代价是：加载固件卷会覆盖上一轮的持久内核日志（console 与 pmsg）。对主力机而言这是丢失排障证据的实质损失，尤其在下一次启动失败时。启动前是否先保留该区内容、或把 FD 迁到别处，属 P2 决策项。

### 3. 启动核实际 MPIDR —— 阻塞

`ArmCpu::probe` 要求 `ml_get_cpu_number(id) == ml_get_boot_cpu_number()`，而 running 标记来自 ADT 的 `state`。E1 不含 `state`，也不含任何运行期启动核信息；Linux 侧的 `cpu-map` 只描述拓扑，不含启动核。

现有只读手段无法取得 MPIDR：`/proc/cpuinfo` 与 DT `reg` 都只反映 affinity，不反映实际运行核。因此本轮不猜测，给出两条并行路径：

- P2 生成器默认以 `cpu@0`（affinity `0x0`）为 running 候选，并在文档与 JSON 中标注为**未证实假设**；
- P3 首轮实机在最早的汇编入口用 `mrs x, mpidr_el1` 写入保留日志区后再继续，用实际值反证或修正该假设。

`ArmDTPlatform` 已内置分级诊断（`sheng-platform-stage` 1–5、`sheng-platform-panic`），可在无串口条件下定位失败阶段，P3 直接复用。

## 八、P2 前置：ADT 必须裁剪

`ArmDTPlatform::createDeviceNubs`（E2 行 87–108）对 `/arm-io` 的**每一个**子节点创建并注册 nub。E1 的 `/soc` 有 **545 个直接子节点**。若直接改名 `/soc` → `/arm-io`，将产生 545 个 nub。

结论：ADT 不能由 Linux FDT 整体转换，必须白名单裁剪到最小集合：

```
/                      根（含 model/compatible）
/chosen                nvram-bank-size, nvram-proxy-data
/cpus                  8 个 cpu@N（剔除 cpu-map），补 state
/arm-io                ranges（24 字节）
/arm-io/intc           reg/compatible/redistributor-stride
/defaults              合成
/options               合成
/psci                  method
```

其余 544 个节点、`/memory`、`/reserved-memory` 一律不进入 ADT；内存信息通过 BootArgs 与 UEFI 分配传递，不通过 ADT 节点。

## 九、待只读采集清单（一次列齐）

以下项目需要设备侧只读操作，本轮未执行：

1. **运行期 EFI 内存图**：确认 `0x84A00000` 与 `0xA7000000–0xA7400000` 的实际类型（`EfiConventionalMemory` 与否）。决定 FD 迁移与 xbl_ramdump 是否需要显式条目。
2. **GOP 模式信息**：分辨率、stride、像素格式。取代 E6 的硬编码几何。
3. **`CurrentEL` 与启动核 MPIDR**：P3 入口日志一并取得，不在 P2 前做。
4. **ramoops 现有内容摘要**：首次 UEFI 启动前记录，作为覆盖前的证据留存。

采集一律只读，不改权限、不挂载、不写分区。

## 十、状态汇总

| 组 | 已证实 | 候选 | 阻塞 |
| --- | --- | --- | --- |
| 平台入口 | `/cpus` 存在 | `/arm-io` 改名、NVRAM 两项 | `/defaults`、`/options` |
| GIC | reg 数值、compatible、stride | ranges 重编码、节点改名 | — |
| CPU | device_type、reg 数值、需剔除 cpu-map | 编码转换 | `state`、唯一 running 核 |
| PSCI | method=`smc` | 路径上提 | — |
| 内存 | DRAM 16 GiB、reg 形态 | 分配窗口、high-RAM | dram-base/size 消费链 |
| 显示 | splash 地址 | — | framebuffer 几何、GOP、EL1 |

P1 可以结项：每个启动必需参数均已定位来源并给出状态，未知项明确为阻塞且写明了缺什么证据。**本轮不生成可启动 ADT，未操作手机。**
