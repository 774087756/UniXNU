# houji 最小 ADT 候选（P2 首件，不可启动）

日期：2026-11-08。产物为离线 ADT 与配套校验，**不是可刷镜像**，未接触手机。

> **格式更正（同日第二轮）**：本文档初版把产物描述为 FDT/DTB，那是错的。DarwinBoot 与 XNU 解析的是 Apple ADT 二进制格式，与 FDT 完全不同。本节记录更正过程与依据，初版结论凡涉及容器的均已作废，语义结论（属性宽度与取值）仍然有效。

## 一、格式更正

### 证据链

1. `drivers/DarwinBoot/.../DarwinBoot.c:535` 在交接前完整遍历 ADT：`AdtNode (Tree, TreeSize, ...) || (Offset != TreeSize)` → `EFI_COMPROMISED_DATA`。
2. `AdtNode`（同文件 185–262 行）的解析方式不是 FDT token，而是：节点头 `UINT32 Properties; UINT32 Children;`（8 字节），属性为 `name[32] + UINT32 Length + value`，每个属性后 `ALIGN_VALUE(offset, 4)`。
3. XNU `pexpert/gen/device_tree.c` 的遍历与之完全一致：`next = align_up(cur + sizeof(DeviceTreeNodeProperty) + length, 4)`，`sizeof(DeviceTreeNodeProperty)` = 32 + 4 = 36。
4. 节点名不是内联字符串，而是名为 `name` 的**属性**：`FindChild` 用 `SecureDTGetProperty(child, "name", ...)` 取得名字。
5. `archive/scripts/make-houji-adt.py` 用的正是 `adt.serialize(tree)` / `adt.parse(blob)`，并以 `parsed.name == 'device-tree'` 做往返校验。

### 两个由此产生的硬约束

- **`nProperties == 0` 的节点其子节点不可达**。XNU 的 `skipProperties()` 在属性数为 0 时返回 `NULL`，而不是节点头之后的位置，于是 `GetFirstChild` 拿到 `NULL`。因此每个节点都必须至少带 `name` 属性——本生成器为每个节点自动写入 `name`，这一条由结构保证，不靠约定。
- **不允许尾部填充**。DarwinBoot 要求遍历恰好消耗整个文件，多一个字节都会被拒。检查器把 `used == len(blob)` 作为硬条件，并有一条负例专门追加 4 字节验证它会被拒。

## 二、决策记录

### FD 区与 ramoops 重叠：接受覆盖，FD 保持 `0xA7100000`

理由不是省事，而是证据强度：`0xA7100000` 是唯一有两个独立文档来源支持的地址——`MemoryMapLib.c` 的 `UEFI_FD` 条目（标注源自 xbl_config 捕获）与 houji `board.toml` 的 `FD_BASE`。迁到任何其他地址都属于无证据猜测，违反「未验证地址不得写入可启动配置」。

代价有界：只有首轮启动会覆盖那一段**已有的**安卓持久日志；之后覆盖的是我们自己的日志。缓解措施是在首次实机启动前记录 ramoops 现状。

### 首轮只放单核：不是保守，是硬约束

XNU `ac9718fb` 的 `machine_routines.c` 三条约束串起来封死了多核：

1. `ml_is_boot_cpu` 对**每个** `/cpus` 子节点调用并读取 `state`，缺失即 `panic("unable to retrieve state for cpu")`。所以每个 CPU 节点都得有 `state`，不是只给启动核。
2. `if (is_boot_cpu) { assert(topology_info.boot_cpu == NULL); ... }` 要求**恰好一个** `running`。
3. `phys_cluster_id = MPIDR_CLUSTER_ID(phys_id)`，即 AFF1。本机 8 核 affinity 为 `0x0…0x700`，AFF1 = 0…7，即 **8 个物理簇**；而 `patches/xnu-12377/native-smp-secondary.patch` 只把 `MAX_CPUS` 从 4 改成 8，`MAX_CPU_CLUSTERS` 仍是 **1**。解析阶段的 `assert(phys_cluster_id <= MAX_CPU_CLUSTER_PHY_ID)` 与 `assert(topology_info.num_clusters < MAX_CPU_CLUSTERS)` 都会先触发。

结论：八核 ADT 在当前补丁下必然 panic，与是否传 `sheng-smp` 无关。该校验已写进检查器。

## 三、交付物

| 文件 | 作用 |
| --- | --- |
| `scripts/houji-adt-format.py` | Apple ADT 格式的序列化与解析，生成器与检查器共用一份定义 |
| `scripts/build-houji-adt.py` | 从本机 FDT 白名单生成最小 ADT 与清单 JSON |
| `scripts/check-houji-adt.py` | 按 DarwinBoot / ArmDTPlatform / ArmCpu / XNU 拓扑契约静态校验，含负例 |

```
python scripts/build-houji-adt.py <live-fdt> <out.adt> [--cpus N] [--window-mib N]
python scripts/check-houji-adt.py <out.adt> --source <live-fdt> --negatives
```

产物（仓库外私有目录，不进版本控制）：

- `houji-adt-min1.adt`：9716 字节，SHA256 `7238f50266a88b02f54775811cb3464d80f96da82f93954ce8eeac986fd5835a`
- `houji-adt-min1.json`：清单与决策记录

同一输入重复生成得到相同哈希（已验证）。

## 四、ADT 内容（10 个节点）

| 节点 | 属性 | 取值 | 来源 |
| --- | --- | --- | --- |
| `device-tree` | `compatible` | `xiaomi,houji\0qcom,sm8650\0AppleARM\0` | 沿用已验证树 |
| | `model` / `manufacturer` / `target-type` | `Xiaomi 14` / `Xiaomi` / `houji` | 同上 |
| `/chosen` | `dram-base` / `dram-size` | 各 8 字节全零 | 沿用已验证树；消费链未定 |
| | `darwinboot-memory-size` | `0x10000000`（256 MiB，8 字节 LE） | 决策，DarwinBoot 窗口 |
| | `firmware-version` | `houji-xnu-12377-uefi\0` | 标识 |
| | `nvram-bank-size` / `nvram-bank-count` / `nvram-current-bank` | 8192 / 1 / 0 | 与历史 fixture 一致 |
| | `nvram-proxy-data` | 8192 字节空白 v1 CHRP | 与历史 fixture **逐字节一致** |
| `/cpus` | — | 仅 `name` | — |
| `/cpus/cpu0` | `device_type` | `cpu\0` | 驱动要求 4 字节 |
| | `reg` | `0x0`（4 字节 LE） | 源 FDT affinity |
| | `compatible` | `qcom,kryo\0ARM,v8\0` | 沿用已验证树 |
| | `state` | `running\0` | 启动核候选 |
| `/arm-io` | `ranges` | `0, 0, 0xFFFFFFFF`（3×LE u64） | 源 FDT `/soc ranges` |
| `/arm-io/intc` | `reg` | `0x17100000, 0x10000, 0x17180000, 0x200000`（4×LE u64） | 源 FDT GIC |
| | `compatible` | `arm,gic-v3\0`（11 字节） | 源 FDT |
| | `redistributor-stride` | `0x40000`（8 字节 LE） | 源 FDT |
| `/defaults` `/options` `/aliases` | — | 仅 `name` | 平台专家要求前两者存在 |
| `/psci` | `method` | `smc\0`（4 字节） | 源 FDT `/soc/psci` |

CHRP 分区与历史 fixture 完全一致：`nvram` 0/32、`common` 32/2064、`free` 2096/6096，合计 8192 字节；bank 的 SHA256 `3c6e675b2f28d917c292a325131c6c868d6ddb82ed8a74fd90c607cdb7fb3525` 与历史 fixture 逐字节相同。

**不含** `/memory`、`/reserved-memory` 及 `/soc` 其余 544 个节点：`createDeviceNubs` 会为 `/arm-io` 每个子节点建 nub，整体转换会产生 545 个 nub。

## 五、校验范围

**格式层**：遍历必须恰好消耗整个文件；每个属性名 32 字节内必须有 NUL；每节点必须有 `name`；深度 ≤ 64；无重复属性名。

**契约层**：根名 `device-tree`；节点白名单（禁止 `memory`、`reserved-memory`、`soc`、`cpu-map`）；节点数 ≤ 16；`/chosen` 三个 4 字节 NVRAM 属性、CHRP 结构（复用 `check-houji-chrp.py`）、窗口大小 256 MiB–8 GiB 且 2 MiB 对齐；每个 CPU 节点有 `device_type` 与 `state`，恰好一个 `running`，`reg` 4 字节且唯一；`arm-io ranges` 24 字节、`intc reg` 32 字节、`compatible` 11 字节、stride 合法且满足驱动下限与总线窗口；`/psci method` 4 字节。

**与源 FDT 的一致性**：ranges、GIC 四元组、stride、PSCI method 逐项回比；每个 CPU affinity 必须存在于源 FDT。这一层防的是「自洽但抄错」。

**负例（10 项全部被拒）**：无 running CPU、两个 running、缺 `state`、混入 `memory`、`ranges` 截断、混入 `cpu-map`、窗口为 0、树尾追加 4 字节、树截断、八核在单簇上限下。

## 六、明确未覆盖

- **`/memory` 与 dram-base/dram-size 消费链**：两项按已验证树置零。P1 已确认 `pe_init.c`、`arm_vm_init.c` 无这两个字符串，但完整链路仍未定。
- **`/defaults` 与 `/options` 内容**：只保证存在。`IODTPlatformExpert::configure` 是否从 `/defaults` 取特定属性未核查。
- **boot-args 通道**：`sheng-platform-stage`、`cpus=` 经 DarwinBoot 的 BootArgs 传入，ADT 不含 `boot-args` 属性。
- **GIC MMIO 可访问性**：所有校验都是编码与边界，没有任何 MMIO 读写。
- **窗口能否分配**：256 MiB 连续 `EfiConventionalMemory` 是否存在，需运行期确认。

## 七、阻塞项

1. **运行期 EFI 内存图**：决定 FD/ramoops 归属、`0x84A00000` 是否需保留、以及 256 MiB 窗口能否分配。
2. **启动核 MPIDR**：`cpu0` 仍是未证实候选。P3 最早入口读 `mpidr_el1` 反证。
3. **多核**：需把 `MAX_CPU_CLUSTERS` 与 `MAX_CPU_CLUSTER_PHY_ID` 提到 ≥ 8 并重新审计。
4. **GOP 几何与 CurrentEL**：`ReadBootVideo` 是前置条件，无采集证据。

## 八、下一步

P2 剩余：引导链写盘路径审查已完成（HOUJI-ANDROID-SAFETY.md），尚缺恢复方案可执行性验证与门禁实测。

boot.img 的组装依赖 Mu-Silicium 检出、aarch64 交叉工具链与已构建的固件卷，本机（Windows）不具备，需在 CI 或 macOS 环境完成。

本轮只做到「主机静态检查通过」，没有任何构建、启动或设备操作。
