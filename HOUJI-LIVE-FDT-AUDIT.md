# houji 实机设备树首次核对

来源：本地只读采集的原始 FDT；961025 字节。
SHA256：`447f252737e719c110495b0b9100d2aac8783265a862f35dd6ae80f820f22ddd`。
采集文件名时间为 2026-11-07T20:26:17Z；不将文件名时间当作固件构建时间。

离线解析遍历了 5064 个节点。原始文件留在仓库外，仅记录筛选后的硬件信息。

| 项目 | 本机 FDT 证据 | 对适配的影响 |
| --- | --- | --- |
| PSCI | `/soc/psci`，`arm,psci-1.0`，method=`smc` | Apple ADT 需要转换为驱动查找的 `/psci` 路径 |
| GIC | `/soc/interrupt-controller@17100000`，`arm,gic-v3` | 新驱动查找 `/arm-io/intc` |
| GICD | 地址 `0x17100000`，长度 `0x10000` | 来自 reg；soc 使用 1 个地址 cell、1 个长度 cell，ranges 为此地址范围的恒等映射 |
| GICR | 地址 `0x17180000`，长度 `0x200000` | 同上；尚未进行 MMIO 读写验证 |
| GICR stride | `0x40000`，1 个 redistributor region | 旧记录的候选 stride 得到本机 FDT 支持 |
| CPU | 8 个 CPU；reg 为 `0x0,0x100,...,0x700`；enable-method=`psci` | `/cpus` 使用 2 个地址 cell；必须解析大端 64 位值后按 ADT 消费方格式编码 |
| 内存 | `/memory/reg` 有 16 个地址/长度元组，包含零长度项 | 不能简化为从某个基址开始的连续 16 GB；不能直接作为 UEFI 分配许可 |
| 保留区域 | `/reserved-memory` 下 58 个节点，包含固定地址、动态分配及零长度项 | 需分别处理；FDT reserve-map 为空不代表没有保留区域 |
| splash | `/reserved-memory/splash_region`：基址 `0xFC400000`、长度 `0x02B00000` | 支持历史 splash 地址；不证明当前 framebuffer 格式、stride 或 GOP 交接有效 |

## 已发现的转换风险

ArmCpu.cpp 的 CPU probe 对 reg 前 4 字节直接 memcpy。当前 Linux FDT 的 CPU reg 前 4 字节全为零，不能直接复制、截断或仅重命名节点。GIC reg、ranges 和 stride 也必须处理 cell 宽度与字节序。

## 下一阶段

1. 对照 houji UEFI MemoryMapLib 的保留区域，列出覆盖与差异；动态池不能用 size 猜基址。
2. 明确 ADT 数值编码及 CPU ID/MPIDR 语义，添加离线转换校验，再生成候选配置。
3. 验证 DarwinBoot 分配和交接约束。尚未生成可刷镜像，也没有实机 XNU 启动证据。

验证范围：自编解析器的头部/边界检查和结构遍历；未使用独立 dtc 交叉验证，不等于完整 binding 或硬件兼容性验证。
