# 小米 14 / iOS 26 开发记录

## 目标与边界

直接研究 iOS 26 移植；已有 iOS 16 houji 实现作为硬件参考。
设备为用户主力机，用户报告已备份、BL 解锁及 Root。
当前仅源码与云端编译阶段；没有启动自定义镜像，没有刷写或修改手机分区。
不记录手机序列号、账号凭据、固件内容或个人备份。

## 固定输入

| 仓库 | 提交 |
| --- | --- |
| lonzzi/UniXNU-houji | 99beb109d66d24d3a1780901cb8958ec3fb24b06 |
| none24smu/UniXNU ios26 | 68c513467bb6c44106c053c410582c1d14f96dd7 |
| none24smu/UniXNU-zeta | eb489285a1d9153872f00c93ebb519a269b249b5 |
| Apple XNU baseline | ac9718fb1af618d5ce8678d0dc6e8a58f252216f / 12377.121.6 |

## 2026-11-07（北京时间）

- 用户 ADB 输出：houji / 23127PN0CC；Android 17，OS4.0.18.0.XNCCNXM；Linux 6.1.138；锁定状态 0；槽位 A；MemTotal 15524336 kB。
- df 查询显示 482G、可用 308G，但挂载点为 /system/etc/hosts；绑定挂载关系未核实，不能据此规划分区。
- houji 清单 2394 个文件哈希匹配；这不是编译或实机验证。
- 用户完成 ios26 的 21 个子模块下载，以及参考设备仓库下载。
- 用户仓库 https://github.com/774087756/UniXNU 已有 ios26 分支。
- GitHub 连接可读取，写入工作流返回 403；后续由用户网页提交工作流。
- CI https://github.com/774087756/UniXNU/actions/runs/42381789615 ：测试对象编译成功，但实际 Xcode 16.4 / SDK 18.5，原检查缺少版本门控，不能算 iOS 26 工具链通过。
- CI https://github.com/774087756/UniXNU/actions/runs/42382200810 ：Xcode 26.6 / iOS SDK 26.5 / ARM64，版本门控和测试对象编译成功。
- 新增 houji-kernel-baseline.yml：固定框架提交，使用上游 XNU 12377 构建脚本；禁用 SM8350 UFS、设备 CPU/platform/USB 及用户空间提供者，先验证基础编译。开启通用架构定时器与 DT panic 选项不等于 houji 硬件适配完成。
- 工作流仅上传日志，不上传 KDK、SDK、IPSW、系统卷或内核二进制。脚本仍需下载依赖与按上游 SHA256 校验的 KDK 头文件输入。
- 此阶段主要框架/XNU 输入固定；构建脚本的部分辅助源码仍使用上游 tag，Homebrew 版本未完全锁定。不得宣称字节级可重复构建。

## 未完成 / 下一步

### 首轮内核 CI（2026-11-07 22:46 北京时间检查）

- 运行：https://github.com/774087756/UniXNU/actions/runs/42382941118
- Job：128434219070。
- checkout、Python 设置、Verify toolchain 均成功；Compile baseline only 正在运行。
- 完整 job 日志下载返回 BlobNotFound（404），当前未取得编译日志；这不是内核编译失败的证据。
- 编译是否通过、内核是否成功链接及产物哈希均待任务结束确认。未进行手机操作。

1. 首轮基础内核编译成功；下一轮接入平台组件并验证链接，不直接进入实机启动。
2. 成功后建立独立 houji 设备配置，移植平台匹配、内存交接、GIC/定时器和日志通道。
3. 核实本机固件/设备树、恢复路径和实际存储挂载；实机测试前单独检查写盘行为。
4. CPU 多核、UFS、用户空间、显示触控、GPU 分阶段验证。

## 更新规则

### 首轮内核 CI 最终结果（2026-11-07）

- Run 42382941118 / Job 128434219070 最终 success；完整日志已读取。
- 22:53:00 北京时间执行 LD，22:53:09 报告 built kernel；文件类型为 Mach-O 64-bit executable arm64。
- 未剥离 noctf 内核大小：22399464 字节。
- SHA256：327dc745abeec0823a885042de84504b7dd3ccf8374d2878871612866e7d85b9。
- 诊断日志 artifact：13578951540；ZIP SHA256 d86da83a87596f36239928e0437350da5981634e4f4d9188d903ff0fc34df31a。
- 日志有编译/链接警告，未阻止本次构建；未宣称无警告。
- 本轮按工作流仅保留日志，内核二进制没有作为 artifact 上传，不应要求用户下载日志后刷写。
- 结论仅为 XNU 12377 基础内核编译链接成功。ArmCpu、ArmDTPlatform、UFS、USB console 等仍关闭，无 houji 实机验证。

每轮记录输入提交、变更、运行链接、实际结果和未解决项。
编译成功不等于实机启动；内核启动不等于 iOS 桌面；桌面不等于可日常使用。

## 2026-11-08：平台组件链接验证准备

- 新增 `.github/workflows/houji-platform-link.yml`，保留已成功的基础工作流不变。
- 启用 XNU_ARMCPU=1、XNU_ARM_DT_PLATFORM=1；架构定时器保持开启。未启用 UFS、USB console、crypto/pthread 提供者。
- 只下载 ArmCpu 与 ArmDTPlatform 子模块，并在 CI 中核对精确提交。
- 检查上游 build-platform-12377.py：使用该轮 XNU 编译记录构建组件；ArmCpu 应用两项上游补丁；验证 ARM64 Mach-O 对象和 iOS 26 deployment 后创建归档，由内核脚本重新链接。
- 此轮仍为通用平台编译链接验证，未添加 houji 设备树、内存布局或实机启动配置。不能将成功结果描述为小米 14 驱动已适配。
- 收集每个组件 compile.log 和 compile-command.json，保留最终内核哈希与完整构建日志；不上传内核二进制。
- 本地四个 shell 块通过 bash -n。当前 Python 缺少 PyYAML，未执行 YAML 解析器检查；macOS 编译须由 CI 验证。
- 状态：本地文件已准备，尚未上传或触发本轮 CI。GitHub 写入权限此前返回 403，由用户网页提交后运行。

### 平台组件 CI 已启动（2026-11-08 11:55 北京时间检查）

- 用户提交运行链接：https://github.com/774087756/UniXNU/actions/runs/42444612478。
- Job 128620809691 状态 in_progress，conclusion 为空；接口没有返回步骤列表。
- 完整日志下载仍返回 BlobNotFound（404）。尚不能确认组件编译、最终链接或产物哈希；这不是构建失败结论。
- 等待任务结束后读取日志并更新最终结果。无手机操作。

### 平台组件 CI 最终结果（2026-11-08）

- Run 42444612478 / Job 128620809691 最终 success。步骤摘要部分字段仍显示旧状态，以完整日志中的组件验证及最终链接为依据。
- ArmCpu、ArmDTPlatform 启用；完整日志显示最终内核链接完成，12:02:02 北京时间报告 built kernel。
- 输出 Mach-O 64-bit executable arm64；未剥离 noctf 内核 22447288 字节。
- 内核 SHA256：3c6b4bbac97361d37006801ce4a2cc14dc8a171366dca6390052621326b13cb5。
- 日志 artifact 13603476006，共 10 个文件；ZIP SHA256 2564d661815a1a75f0720324bc5f4d5784e4d306e23fd762023736d8f52b2030。
- 通用平台组件编译链接验证通过；仍有构建警告。没有 houji 实机启动证据。
- 下一步从通用编译转入 houji 引导/设备树/内存布局接口核对，准备设备专用最小配置。不能直接刷本轮内核，且本轮未上传内核二进制。

## 2026-11-08：计划书与 P1 首轮审计

- 新增 HOUJI-PROJECT-PLAN.md，列出 P0-P6、交付/验收、主力机边界、分工和记录规则。
- 已核查具体接口差异：旧 SweetPlatformExpert.cpp 的 processTopLevel 绕开原 NVRAM 发布路径；新 ArmDTPlatform.cpp 要求 /chosen 中有效 nvram-bank-size 与 nvram-proxy-data，并需要 options/cpus/arm-io/defaults。旧 ADT 不能未经校验直接复用。
- 新 ArmCpu.cpp 读取 /arm-io/intc 的 reg/compatible/redistributor-stride，以及 /arm-io ranges；PSCI method 来自 /psci，不默认选择 smc/hvc。旧平台代码排除名为 gic 的子节点，尚需检查实际 ADT 生成器以确定节点转换，不能仅靠命名推断地址。
- houji MemoryMapLib.c 标注源于一次捕获的 xbl_config，SHA256 为 1fd55850171f68f8658c2342820b76ee60d28733dfcc93ad365dd43e660f490d；包含硬编码保留区，尚未与用户本机固件匹配。不因设备同为 houji 就视为已验证。
- 下一步继续定位 ADT 生成入口与 DarwinBoot 补丁，形成参数来源表，再列出必要的本机只读采集项。未修改启动地址、未生成实机候选。

### P1 启动接口审计进展

- 新增 HOUJI-BOOT-AUDIT.md：记录 NVRAM、GIC、CPU/PSCI、内存、显示及生成器来源。
- 修正前述推断：旧 SweetPlatformExpert 绕开 NVRAM 发布路径，并不意味着旧 ADT 没有 NVRAM。archive/scripts/make-houji-adt.py 明确生成 8 KiB CHRP proxy；仍须验证新内核兼容性。
- 已找到旧生成器；其位于 archive、依赖外部固定 reference，未当作当前有效构建入口执行。
- 明确阻塞：旧 gic 节点与新 intc 契约不同；历史 0x40000 stride、帧缓冲地址和 xbl 内存图尚未对本机核实。
- 下一步只读检查本机原始 FDT 的可访问性，随后设计字节不损坏的本地采集；不刷写、不重启、不改权限。

### 本机 FDT 采集准备

- 用户输出确认 ro.soc.model=SM8650、ro.boot.hardware=qcom；bootloader 属性为空，不据此推断版本。
- /sys/firmware/fdt 普通 shell 权限不足；展开设备树目录可列出 cpus/memory/reserved-memory/soc 等。
- xbl_config_a 指向 /dev/block/sdb2，xbl_config_b 指向 /dev/block/sdc2；仅路径存在，不代表内容已读取或匹配。
- 新增 scripts/collect-houji-fdt.py：只允许一个已授权 houji，以 adb exec-out + su cat 读取 FDT，在电脑私有目录保存原始字节，不写手机、不读 xbl 分区。
- 主机验证：合法头部通过；文本错误、截断和错误 magic 均拒绝。尚未实际采集；头部校验不等于完整 FDT 语义验证。

### FDT collection retry: remote command quoting
- User reported FDT magic validation failure; no DTB was saved.
- Corrected remote shell quoting: adb must preserve the complete cat command as the argument to su -c. This is a suspected cause, pending device verification.
- Added bounded text/hex diagnostics and a clean failure message. Binary device tree contents are not printed.
- CLI help check passed. No phone writes or reboot performed; real-device retry remains pending.

### FDT collection blocked: su unavailable to ADB shell
- Retry returned 46 bytes of text: /system/bin/sh: su: inaccessible or not found.
- FDT was not read and no DTB was saved. Current evidence establishes only that su is unavailable/inaccessible in this shell; it does not establish that the phone is unrooted.
- Next: user checks root manager status and read-only shell PATH/command lookup. No partition or root configuration changes performed.

### Root availability check
- User reports uid=2000(shell), SELinux context u:r:shell:s0; command -v su returned no path.
- /system/bin/su, /system/xbin/su, /sbin/su, /debug_ramdisk/su all returned No such file or directory.
- Root access from ADB remains unavailable. This does not distinguish inactive root from manager-specific restrictions. Awaiting root manager name and current status before proposing any configuration change.
- Raw FDT collection remains blocked; no phone writes performed.

### ADB root access verified
- User ran adb shell su -c id and received uid=0(root), gid=0(root), context=u:r:ksu:s0.
- KernelSU root execution is now verified for ADB shell. Live FDT collection can be retried using the existing read-only collector.
- FDT acquisition and hardware analysis remain pending; no boot/flash operations performed.

### Live FDT acquired and inspected offline
- Verified local 961025-byte FDT SHA256 447f252737e719c110495b0b9100d2aac8783265a862f35dd6ae80f820f22ddd against user output.
- Added scripts/inspect-houji-fdt.py; traversed 5064 nodes. Selected results in HOUJI-LIVE-FDT-AUDIT.md.
- Confirmed PSCI smc, GICD 0x17100000, GICR 0x17180000, stride 0x40000, eight CPU nodes. CPU reg is big-endian 64-bit; ArmCpu reads first 32 bits, so raw copying is invalid.
- Memory has 16 tuples; reserved-memory has 58 children. Splash reservation matches historical address but framebuffer geometry remains unverified.
- No phone commands, flashing or MMIO accesses performed during offline analysis. Next: UEFI memory map comparison and ADT encoding validation.

### Offline UEFI memory comparison and ADT contract
- Added audit-houji-memory.py and generated HOUJI-MEMORY-COMPARISON.md from 41 literal UEFI descriptors, 41 nonzero fixed FDT reservations, and 15 nodes lacking reg; two zero-sized demura entries excluded.
- Identified XBL_Ramdump/qlink naming-address mismatch and ramoops overlap with FD_Reserved/UEFI_FD. These require lifecycle/current firmware verification, not automatic relocation.
- Added HOUJI-ADT-CONTRACT.md with explicit little-endian widths, GIC values and unresolved CPU ID semantics. High RAM coverage alone is not allocation approval.
- Passed interval boundary checks and GIC encoding/range checks. No bootable configuration produced; no phone operations performed.

### CPU affinity and DarwinBoot handoff audit
- Confirmed ArmCpu reg carries physical affinity through ml_get_cpu_number, info.phys_id and PSCI CPU_ON; do not replace with sequential logical indices.
- Added prepare-houji-adt-contract.py and HOUJI-ADT-CANDIDATE.json, explicitly nonbootable. Real FDT conversion/round-trip checks and malformed input rejection passed.
- Added HOUJI-DARWINBOOT-HANDOFF.md: EL1, GOP prerequisite, actual contiguous UEFI allocation, 256 MiB default, 256 MiB-8 GiB explicit parser range, and ExitBootServices failure boundary.
- Corrected earlier generic assumption: current Boot implementation does not visibly patch ADT dram-base/size; BootArgs are populated from allocation. Exact XNU topology and ADT consumers remain to verify.
- No phone writes, boots or driver changes performed.

### 2026-11-08 progress and pinned XNU topology audit
- P0 toolchain/kernel/platform compile milestones complete; P1 offline board adaptation ongoing. No bootable image or on-device XNU boot established.
- Read Apple machine_routines.c at pinned ac9718fb1af618d5ce8678d0dc6e8a58f252216f via GitHub; checked local topology-related patch scope.
- Confirmed mandatory CPU state, running boot CPU selection, sequential accepted logical IDs, AFF1/AFF0 physical lookup, and one-cluster/eight-CPU patch limits. Linux cpu-map cannot be copied as a direct cpus child.
- Added HOUJI-XNU-TOPOLOGY-AUDIT.md and refreshed nonbootable candidate blockers. Real-FDT generator rerun passed.
- Previous handoff document's missing-source statement describes the earlier stage; pinned CPU source is now reviewed. Actual boot MPIDR, full ADT/CHRP requirements and UEFI memory ownership remain unverified.

### CHRP fixture validation
- Read pinned Apple IONVRAM.cpp and IONVRAMCHRPHandler.cpp; confirmed bank length and Adler requirements, generation offset 20, 16-byte CHRP blocks.
- Added check-houji-chrp.py and HOUJI-NVRAM-AUDIT.md. Historical 8192-byte fixture passed model checks; four corruption/bounds cases rejected.
- No Apple handler execution claimed. Full getNVRAMProperties/unserialize/publication chain and complete ADT validation remain pending.
- Read pinned pe_init.c and arm_vm_init.c; no dram-base/dram-size strings there. This is only scoped negative evidence, not proof those properties are unused globally.
- No phone operation or bootable artifact generated.

## 2026-11-08：资产归位与远端同步

- 提交前盘点：ios26 工作副本相对 68c5134 有 18 个未跟踪文件（10 份 HOUJI 文档、1 份 ADT 候选 JSON、5 个脚本、3 个工作流），远端两个仓库均无。此前它们只存在于本机。
- 核对工作流一致性：三个 workflow 与 fork main 上已实际运行的版本内容相同，差异仅为 CRLF/LF；`.gitattributes` 为 `* text=auto eol=lf`，提交时自动归一为 LF。
- 补装 PyYAML 6.0.3（此前本机缺失，工作流只做过 `bash -n`），对三个 workflow 执行真实 YAML 解析：均通过，job/触发/steps 结构与预期一致；HOUJI-ADT-CANDIDATE.json 解析通过，status 仍为 OFFLINE_CONTRACT_ONLY_NOT_BOOTABLE。
- 按显式文件清单提交（未使用 `git add` 全目录），提交 20feee8，18 文件 1079 行。提交身份为仓库级 774087756 <774087756@users.noreply.github.com>。
- 推送成功：68c5134..20feee8 → fork 774087756/UniXNU 分支 ios26，远端已核对为 20feee8。GitHub 写入此前返回 403，本轮已恢复，不再需要网页提交工作流。
- 新增本地远端 `fork` 指向 774087756/UniXNU；`origin` 仍为上游 none24smu/UniXNU。
- 已知结构性问题：三个工作流的 checkout 固定为 `repository: none24smu/UniXNU`、`ref: 68c5134`，本地/fork 提交不参与 CI 构建。若要让 CI 验证 fork 上的改动，须改 workflow 的 repository/ref，属下一轮待决项。
- 边界：本轮未修改任何源码、未触发新 CI、未操作手机、未生成可启动产物。

## 2026-11-08：P1 结项（参数来源表）

- 新增 HOUJI-PARAM-PROVENANCE.md：按平台入口、GIC、CPU/拓扑、PSCI、内存、显示六组列出每个启动必需参数的消费方要求、来源证据、目标取值与状态（已证实/候选/阻塞）。
- 证据全部来自本机 FDT（SHA256 447f2527…）、ArmDTPlatform.cpp、ArmCpu.cpp、Apple XNU ac9718fb、houji MemoryMapLib.c 与历史 ADT 生成器。未引入新推断。
- 三个未决项结论：
  1. `XBL_Ramdump` 条目范围正确、名称错误。FDT 精确证据：`qlink_logging_region@84800000`=0x84800000+0x200000，`xbl_ramdump_region@84a00000`=0x84A00000+0x200000。该条目地址长度与 qlink 一致，与 xbl_ramdump 不一致。真正的 xbl_ramdump 区在内存表中无条目；是否需补取决于运行期 EFI 内存图，本轮未读取，不判定为缺陷。
  2. ramoops 与 FD 区为所有权交接而非地址冲突。FDT `ramoops_region`=0xA7000000+0x400000（唯一覆盖该范围的保留节点，console-size 与 pmsg-size 各 0x200000，无 no-map）；内存表 `FD_Reserved`(1 MiB)+`UEFI_FD`(3 MiB) 合计恰好 4 MiB 与之完全重合。实际代价是加载固件卷会覆盖上一轮持久内核日志，属 P2 决策项。
  3. 启动核 MPIDR 仍阻塞。FDT 无 `state`，Linux `cpu-map` 只描述拓扑不含启动核，`/proc/cpuinfo` 与 DT `reg` 都只反映 affinity。不猜测：P2 以 cpu@0 为未证实候选，P3 在最早入口读 `mpidr_el1` 反证。
- 本轮新发现（影响 P2 实现方式）：
  - `ArmDTPlatform::createDeviceNubs` 为 `/arm-io` 每个子节点建 nub，而本机 `/soc` 有 545 个直接子节点。ADT 必须白名单裁剪到最小集合，不能整体改名转换。
  - `/soc ranges` 为 16 字节而非 12 字节：`/soc` 声明 1 个地址 cell，父节点 `/` 声明 2 个，故条目为 1+2+1=4 cell。按 3 cell 解析会错位；24 字节目标值必须重新编码。
  - `/cpus` 含 `cpu-map`（Linux 专用）。现有生成器已按 `device_type` 过滤，风险在整体转换路径。
- 未改动 HOUJI-ADT-CANDIDATE.json：现有生成器逻辑与上述结论一致（ranges 已按 `>IQI` 处理 4 cell，CPU 已按 device_type 过滤），重新生成结果不变。
- 边界：P1 可结项，但仍无运行期 EFI 内存图、GOP 几何、CurrentEL/MPIDR。本轮未生成可启动 ADT，未操作手机。

## 2026-11-08：P2 首件（最小 ADT 生成与校验）

- 用户授权自行决策。决策一：FD 保持 `0xA7100000`，接受覆盖 ramoops。理由是该地址有 `MemoryMapLib.c` 与 `board.toml` 两个独立来源，迁移即无证据猜测。遗留矛盾（原厂若在此加载固件卷则 pstore 失效）未解决，列为阻塞项，靠运行期 EFI 内存图定案。
- 读 XNU `ac9718fb` `machine_routines.c` 确认三条拓扑约束：`state` 对每个 CPU 节点都必需且缺失即 panic；`assert(boot_cpu == NULL)` 要求恰好一个 running；`phys_cluster_id = AFF1`，本机 8 核为 0…7 共 8 个物理簇，而 `patches/xnu-12377/native-smp-secondary.patch` 只改 `MAX_CPUS` 4→8、`MAX_CPU_CLUSTERS` 仍为 1。结论：八核 ADT 必然触发 `assert(phys_cluster_id <= MAX_CPU_CLUSTER_PHY_ID)`，与 `sheng-smp` 无关；单核是唯一可解析形态。
- 新增 `scripts/build-houji-adt.py`：白名单生成最小 ADT，不转换 Linux 树。根名 `device-tree`；9 个节点（root、chosen、cpus+cpu@0、arm-io+intc、defaults、options、psci）；不含 `/memory`、`/reserved-memory`、cpu-map 及 `/soc` 其余节点。CHRP bank 由脚本内联合成（nvram 0/32、common 32/2064、free 2096/6096）。
- 新增 `scripts/check-houji-adt.py`：按 ArmDTPlatform、ArmCpu、XNU 拓扑契约校验，并逐项回比源 FDT（ranges、GIC 四元组、stride、PSCI、CPU affinity），防「自洽但抄错」。CHRP 校验复用 `check-houji-chrp.py`，单一来源。
- 产物（仓库外私有目录）：`houji-adt-min1.dtb` 8784 字节，SHA256 `5f0e78856654152bf2a86b1a755824e6f08188961b6c6767d01ad26af72bf3a1`；同输入重复生成哈希一致。
- 校验结果：PASS，9 节点、1 CPU（affinity 0x0）、1 running、1 簇；7 项负例全部被拒（无 running、双 running、缺 state、混入 /memory、ranges 截断、混入 cpu-map、八核在单簇上限下）。八核检查已固化为规则而非文档描述。
- 新增 HOUJI-P2-ADT-CANDIDATE.md 记录决策、约束推导、节点表与未覆盖项。
- 明确未覆盖：`/memory` 与 dram-base/size 消费链、`/defaults` 与 `/options` 属性集、根节点属性、boot-args 通道、GIC MMIO 可访问性。
- 下一步：引导链写盘路径审查（UEFI、DarwinBoot、`fastboot boot` 边界）与恢复方案可执行性验证。本轮无构建、无启动、无设备操作。

## 2026-11-08：写盘路径审查与「不影响安卓」契约

- 用户要求：不影响安卓的情况下启动 iOS。已固化为 HOUJI-ANDROID-SAFETY.md：判定标准、证据、禁止清单、门禁检查表。
- 代码级证据（全部指向默认配置无持久写路径）：`APRIORI.inc` 注释声明第一阶段无 storage/USB mass-storage/capsule/OEM updater；`DXE.inc` 注释声明变量使用 RAM 模拟存储，并含 `NoCapsuleRuntimeDxe`；`houji.dsc` 无任何 `PcdFlashNvStorage*`；`RAM.inc` 注释声明唯一块设备是只读内存盘、无物理磁盘控制器；`WITH_HOUJI_UFS_MMIO` 默认 FALSE；`DarwinBoot.c:84` 以 `EFI_FILE_MODE_READ` 只读打开。
- 实机级证据（同机型先例）：`UniXNU-houji/docs/device-tests.md` 第 5、77、208、227 行记录多轮 `fastboot boot` 临时启动，明确「启动分区、GPT 与 misc 均未改变」，并曾进入 iOS 桌面后返回 Recovery。本机型 `fastboot boot` 可用这一最大前置未知已由先例解决。
- 阶段判断：P3 内核启动与约束完全兼容（全链 RAM 内）。P4 用户空间与约束直接冲突——上游 `docs/concepts/userdata.md` 以 userdata 承载 Darwin 根卷（`SHNGROOT` 窗口），houji 使用 32 GiB HFSX 系统卷；该记录只声明 boot/GPT/misc 未变，从未声明 userdata 未变，故根卷很可能占用 userdata。
- 待用户确认：当年是否牺牲了安卓数据。若已牺牲，则「不影响安卓」与「iOS 用户空间」在现有方案下不可兼得，需在外接 USB 存储（B）与 userdata 内文件（C）之间选择，两者均需新驱动，不在 P2/P3 展开。
- 新增 `scripts/fingerprint-android-state.py`：只读计算 `misc`、`boot_a`、`vbmeta_a`、`dtbo_a`、`init_boot_a` 与分区表清单的 SHA256，供启动前后比对。全程 `adb exec-out su -c 'cat ...'` 管道读取，不在设备端写文件、不改权限、不挂载、不重启。局限已在脚本与文档中声明：GPT 以分区清单近似，不改尺寸与偏移的改名不会反映。
- 未执行：脚本未对设备运行（需用户授权），`fastboot boot` 未在本机实测，无任何设备操作。
- 下一步：恢复方案可执行性验证、门禁实测（启动前后指纹比对），以及根卷存储路线决策。
