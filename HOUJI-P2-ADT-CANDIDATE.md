# houji 最小 ADT 候选（P2 首件，不可启动）

日期：2026-11-08。产物为离线 ADT 与配套校验，**不是可刷镜像**，未接触手机。

## 一、决策记录

### FD 区与 ramoops 重叠：接受覆盖，FD 保持 `0xA7100000`

理由不是省事，而是证据强度：`0xA7100000` 是唯一有两个独立文档来源支持的地址——`MemoryMapLib.c` 的 `UEFI_FD` 条目（标注源自 xbl_config 捕获）与 houji `board.toml` 的 `FD_BASE`。迁到任何其他地址都属于无证据猜测，违反「未验证地址不写入可启动配置」。

代价有界：只有首轮启动会覆盖那一段**已有的**安卓持久日志；之后覆盖的是我们自己的日志。缓解措施是在首次实机启动前记录 ramoops 现状。

**遗留矛盾（不假装解决）**：若原厂 UEFI 真在此处加载固件卷，则 ramoops 每次开机都会被清空，pstore 将失去意义。因此要么原厂并不在此加载，要么该段的归属另有解释。这一点只能靠运行期 EFI 内存图定案，已列为 P2 阻塞项。

### 首轮只放单核：不是保守，是硬约束

已读 XNU `ac9718fb` 的 `machine_routines.c`，三条约束串起来封死了多核：

1. `ml_is_boot_cpu` 对**每个** `/cpus` 子节点调用并读取 `state`，缺失即 `panic("unable to retrieve state for cpu")`。所以 8 个节点都得有 `state`，不是只给启动核。
2. `if (is_boot_cpu) { assert(topology_info.boot_cpu == NULL); ... }` 要求**恰好一个** `running`。
3. `phys_cluster_id = MPIDR_CLUSTER_ID(phys_id)`，即 AFF1。本机 8 核 affinity 为 `0x0…0x700`，AFF1 = 0…7，即 **8 个物理簇**；而 `patches/xnu-12377/native-smp-secondary.patch` 只把 `MAX_CPUS` 从 4 改成 8，`MAX_CPU_CLUSTERS` 仍是 **1**。解析阶段的 `assert(phys_cluster_id <= MAX_CPU_CLUSTER_PHY_ID)` 与 `assert(topology_info.num_clusters < MAX_CPU_CLUSTERS)` 都会先触发。

结论：八核 ADT 在当前补丁下必然 panic，与是否传 `sheng-smp` 无关。单核 ADT 是唯一能过拓扑解析的形态。该校验已写进检查器，不是文档里的一句话。

## 二、交付物

| 文件 | 作用 |
| --- | --- |
| `scripts/build-houji-adt.py` | 从本机 FDT 白名单生成最小 ADT 与清单 JSON |
| `scripts/check-houji-adt.py` | 按 ArmDTPlatform / ArmCpu / XNU 拓扑契约静态校验，含负例 |

生成：

```
python scripts/build-houji-adt.py <live-fdt> <out.dtb> [--cpus N]
```

产物（留在仓库外的私有目录，不进版本控制）：

- `houji-adt-min1.dtb`：8784 字节，SHA256 `5f0e78856654152bf2a86b1a755824e6f08188961b6c6767d01ad26af72bf3a1`
- `houji-adt-min1.json`：清单与决策记录

同一输入重复生成得到相同哈希（已验证），不依赖时间戳或随机序。

## 三、ADT 内容（9 个节点）

| 节点 | 属性 | 取值 | 来源 |
| --- | --- | --- | --- |
| `device-tree` | — | 无属性 | 根名由平台专家匹配要求 |
| `/chosen` | `nvram-bank-size` | `0x2000`（4 字节 LE） | 合成 |
| | `nvram-proxy-data` | 8192 字节空白 v1 CHRP | 合成 |
| `/cpus` | `#address-cells` / `#size-cells` | 1 / 0 | 合成 |
| `/cpus/cpu@0` | `device_type` | `cpu\0` | 源 FDT |
| | `reg` | `0x0`（4 字节 LE） | 源 FDT affinity |
| | `state` | `running\0` | 合成（启动核候选） |
| `/arm-io` | `ranges` | `0, 0, 0xFFFFFFFF`（3×LE u64 = 24 字节） | 源 FDT `/soc ranges` |
| `/arm-io/intc` | `reg` | `0x17100000, 0x10000, 0x17180000, 0x200000`（4×LE u64 = 32 字节） | 源 FDT GIC |
| | `compatible` | `arm,gic-v3\0`（11 字节） | 源 FDT |
| | `redistributor-stride` | `0x40000`（8 字节 LE） | 源 FDT |
| `/defaults` | — | 空节点 | 合成，平台专家要求存在 |
| `/options` | — | 空节点 | 同上 |
| `/psci` | `method` | `smc\0`（4 字节） | 源 FDT `/soc/psci` |

CHRP 分区与历史 fixture 完全一致：`nvram` 0/32、`common` 32/2064、`free` 2096/6096，合计 8192 字节。

**不含** `/memory`、`/reserved-memory` 及 `/soc` 其余 544 个节点。原因见 P1 文档：`createDeviceNubs` 会为 `/arm-io` 每个子节点建 nub，整体转换会产生 545 个 nub。

## 四、校验范围

检查器验证两类内容：

**契约符合性**：根名为 `device-tree`；节点白名单（含禁止 `/memory`、`/reserved-memory`、`cpu-map`、`/soc`）；节点数 ≤ 16；`/chosen` 两项宽度与 CHRP 结构（复用 `check-houji-chrp.py` 的校验器，单一来源）；每个 CPU 节点有 `device_type` 与 `state`，恰好一个 `running`，`reg` 为 4 字节且 affinity 唯一；`arm-io ranges` 恰好 24 字节、`intc reg` 恰好 32 字节、`compatible` 恰好 11 字节、stride 在允许集合内且满足驱动下限与总线窗口；`/psci method` 4 字节。

**与源 FDT 的一致性**：ranges、GIC 四元组、stride、PSCI method 逐项回比源 FDT；每个 CPU affinity 必须存在于源 FDT。这一层防的是「自洽但抄错」。

**负例（7 项全部被拒）**：无 running CPU、两个 running CPU、缺 `state`、混入 `/memory`、`ranges` 截断为 16 字节、混入 `cpu-map`、八核树在 `MAX_CPU_CLUSTERS=1` 下。

## 五、明确未覆盖

- **dram-base / dram-size**：`/memory` 节点未生成。P1 已确认 `pe_init.c`、`arm_vm_init.c` 无这两个字符串，DarwinBoot 通过 BootArgs 传递窗口，但完整消费链仍未定。这是本轮最大的未知。
- **`/defaults` 与 `/options` 内容**：只保证存在，属性集未确定。`IODTPlatformExpert::configure` 是否从 `/defaults` 取特定属性未核查。
- **根节点属性**：当前完全为空。平台专家按根名匹配，是否需要 `model`/`compatible` 未验证。
- **boot-args 通道**：`sheng-platform-stage`、`cpus=` 等参数经 DarwinBoot 的 BootArgs 传入，本 ADT 不含 `boot-args` 属性。该通道未验证。
- **GIC 可访问性**：所有 GIC 校验都是编码与边界，没有任何 MMIO 读写。

## 六、阻塞项

1. **运行期 EFI 内存图**：决定 FD/ramoops 归属，以及 `0x84A00000` 是否需显式保留。
2. **启动核 MPIDR**：`cpu@0` 仍是未证实候选。P3 最早入口读 `mpidr_el1` 反证。
3. **多核**：需把 `MAX_CPU_CLUSTERS` 与 `MAX_CPU_CLUSTER_PHY_ID` 提到 ≥ 8 并重新审计，才能解除单核限制。
4. **GOP 几何与 CurrentEL**：`ReadBootVideo` 是前置条件，无采集证据。

## 七、下一步

P2 剩余工作：引导链写盘路径审查（UEFI、DarwinBoot、`fastboot boot` 边界）与恢复方案可执行性验证。这一步完成后才谈实机，且需用户明确授权。

本轮只做到「主机静态检查通过」，没有任何构建、启动或设备操作。
