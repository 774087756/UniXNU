# 「不影响安卓」启动约束（硬性设计契约）

日期：2026-11-08。本文件把用户要求「不影响安卓的情况下启动 iOS」固化为可判定的契约，并区分**已证实安全**与**存在冲突**两部分。

## 一、什么叫「不影响」

判定标准是持久存储的字节不变，不是「能开机」。满足以下全部条件才算通过：

1. 不写 `boot` / `init_boot` / `vendor_boot` / `dtbo` / `vbmeta` / `super` / `userdata` 任一分区。
2. 不改 GPT、不改槽位（slot）、不改 `misc`（含 bootcontrol 与 bootcount）。
3. 不安装或替换 recovery、不修改 AVB 状态。
4. 不断电重启后，安卓仍能正常启动且数据完整。
5. 全程可用长按电源键回到安卓，无需任何恢复镜像。

## 二、已证实的无写盘证据

### 代码级（UEFI 阶段）

| 证据 | 位置 | 含义 |
| --- | --- | --- |
| `// No storage, USB mass-storage, capsule or OEM updater in stage 1.` | `houjiPkg/Include/APRIORI.inc` | 第一阶段固件不含存储、USB 大容量、胶囊与 OEM 更新器 |
| `// Variables use the emulated RAM store.` | `houjiPkg/Include/DXE.inc` | UEFI 变量为 RAM 模拟，不落分区 |
| 无 `PcdFlashNvStorage*` / `Pcd*Variable*` PCD | `houji.dsc` | 没有 Flash 变量存储地址，变量无处可持久化 |
| `NoCapsuleRuntimeDxe` | `DXE.inc` | 胶囊更新路径被显式移除，阻断固件写入 |
| `// Only this read-only memory block device supplies Block I/O. No physical disk controller.` | `houjiPkg/Include/RAM.inc` | 唯一的块设备是只读 RAM 盘，没有物理磁盘控制器 |
| `WITH_HOUJI_UFS_MMIO = FALSE`（默认） | `houji.dsc` | UFS MMIO 默认不映射 |
| `Root->Open (..., EFI_FILE_MODE_READ, 0)` | `DarwinBoot.c:84` | DarwinBoot 只以只读方式打开文件 |
| `nvram-proxy-data` 为 DT 内 8192 字节易失 bank | P2 ADT | XNU 的 NVRAM 来自内存，不写硬件 |

结论：整条 UEFI 与 XNU 引导链在默认配置下没有可达的持久写路径。这是设计使然，不是巧合。

### 实机级（同机型先例）

`UniXNU-houji` 的 iOS 16 移植在同一台设备（houji / 23127PN0CC / SM8650）上多轮验证：

- `docs/device-tests.md:5`：小米 14 从 OrangeFox 经 `fastboot boot` 临时启动，**未刷写启动分区或改变 GPT**。
- `docs/device-tests.md:208`：**启动分区、GPT 与 misc 均未改变**。
- `docs/device-tests.md:227`：**启动分区、GPT 与 misc 未改变**。
- `docs/device-tests.md:77`：经 `fastboot boot` 临时启动，确认**进入桌面并返回 OrangeFox**。

因此 `fastboot boot` 在本机型可用，且已被证明可在不改动上述分区的前提下进入 iOS 桌面。这解决了本项目最大的前置未知。

## 三、分阶段的可行性判断

| 阶段 | 是否满足约束 | 依据 |
| --- | --- | --- |
| P3 内核启动 | **满足** | 全链在 RAM 内：`fastboot boot` 载入 BootShim + UEFI FV，payload 由只读 RAM 盘提供内核与 ADT，无分区访问 |
| P4 iOS 用户空间 | **与约束直接冲突** | iOS 根卷需要数十 GiB 持久存储，上游模型把它放在 userdata |

### P4 冲突的具体情况

上游 `docs/concepts/userdata.md` 的模型是：userdata 分区承载 Darwin 根文件系统，以 `SHNGROOT` 清单划分窗口（`OS`、`SystemOS`），对应 `fastboot flash userdata <image>`。houji 的 iOS 16 移植使用 **32 GiB HFSX 卷**作为系统卷。

需要注意：houji 的记录反复声明「启动分区、GPT 与 misc 未改变」，但**从未声明 userdata 未改变**。按上游模型推断，该根卷很可能占用了 userdata——也就是当年很可能牺牲了安卓数据。

**这一点必须由用户确认**：如果当年确实改写了 userdata，那么「不影响安卓」与「运行 iOS 用户空间」在现有方案下不可兼得，需要新方案。

## 四、根卷方案选项（P4 决策项，非本轮实施）

| 方案 | 做法 | 对安卓的影响 | 代价 |
| --- | --- | --- | --- |
| A 仅到内核 | 不做用户空间，止步于 P3 | 无 | 看不到桌面，只验证内核 |
| B 外接 USB 存储 | 根卷放 U 盘/移动硬盘，XNU 走 xHCI host | 无 | 需 XNU 侧 xHCI host + USB 存储驱动；手机需 OTG 供电 |
| C userdata 内文件 | 根卷作为 `/data` 下的普通文件，驱动按文件 extent 读块 | 无（只读挂载） | 需 f2fs/ext4 读取器，工程量最大 |
| D 现有未用分区 | 借用 `cust` 等分区 | **有**（改写了分区内容） | 已排除：本机无 `cust` 分区，见 HOUJI-DEVICE-BASELINE.md |
| E 缩小 userdata 后重划分 | 收缩文件系统腾出空间 | **有**（重分区风险极高） | 违反禁止清单 |

实测数据（2026-11-08，只读采集）：`userdata` 482 GiB，已用 173 GiB，**可用 309 GiB**；`super` 7.8 GiB；无 `cust`。按 houji iOS 16 移植的 32 GiB 系统卷估算，**容量不是瓶颈**——障碍在于 XNU 需要块级访问，而 `/data` 是 f2fs 上的文件。这一点让 B 与 C 的取舍更清晰：B 绕开文件系统解析，代价是外设与 xHCI 驱动；C 不需要外设，代价是 f2fs 解析器。

初判：B 与 C 是唯二不违反契约的路线，B 的驱动面比 C 小，但依赖 OTG 与外部供电；C 不需要外设但需要文件系统解析。两者都应在 P4 之前单独做可行性评估，不在 P2/P3 展开。

## 五、首轮实机门禁（必须全部满足才可启动）

1. `fastboot boot` 在本机可用——已有同机型先例，仍需在本机实测一次。
2. 启动镜像只含 BootShim + UEFI FV + payload，**不含任何分区写指令**。
3. payload 体积在 RAM 盘容量内，且与内存窗口不冲突。
4. 已记录启动前的分区指纹（见第六节），启动后逐项比对。
5. 用户已明确授权本轮实机操作。
6. 恢复手段明确：长按电源键 → 正常引导安卓。因未写分区，此路径不依赖任何镜像。

## 六、前后指纹比对

`scripts/fingerprint-android-state.py` 以只读方式计算关键对象的哈希：`misc`、`boot_a`、`vbmeta_a`、`dtbo_a` 与主 GPT。启动前后各跑一次，逐项比对。

只读实现：全部通过 `adb exec-out su -c 'cat ...'` 管道读取，不写任何设备端文件，不改权限、不挂载、不重启。脚本只输出指纹，不打印分区内容。

比对通过的含义是「上述对象字节未变」，不覆盖未列出的分区；如需更严格，可扩展到全部分区，但耗时显著增加。

## 七、禁止清单（任何情况下不做）

- `fastboot flash` 任何分区，包括「临时刷入再恢复」。
- 切换 slot、`fastboot set_active`、修改 `misc`。
- 重分区、格式化、`fastboot -w`。
- 安装或替换 recovery、修改 vbmeta / AVB 状态。
- 在设备上创建持久文件、改权限、挂载新文件系统。
- 未取得用户当轮明确授权的任何写操作。

## 八、当前结论

**P3（内核启动）与约束完全兼容，且已有同机型先例支撑。**

**P4（iOS 用户空间）与约束冲突**，冲突根源是根卷的持久存储位置。在选定 B 或 C 路线之前，不推进用户空间，也不以「先刷一下试试」的方式绕过。

本轮未执行任何设备操作，未生成可启动镜像。
