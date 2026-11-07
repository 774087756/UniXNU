# houji ADT 转换约定（离线设计，尚非启动配置）

输入证据：HOUJI-LIVE-FDT-AUDIT.md 指定的 FDT。消费方：当前 drivers/ArmCpu/ArmCpu.cpp 的 probe/mapGic。

| 输出位置 / 属性 | 编码约定 | 候选值 |
| --- | --- | --- |
| /arm-io ranges | 3 个小端 uint64，24 字节 | 子总线基址 0、物理基址 0、跨度 0xFFFFFFFF；源为 /soc ranges 的数值解码 |
| /arm-io/intc reg | 4 个小端 uint64，32 字节 | 0x17100000、0x10000、0x17180000、0x200000 |
| /arm-io/intc compatible | 带 NUL 字符串，11 字节 | arm,gic-v3 |
| /arm-io/intc redistributor-stride | 小端 uint64，8 字节 | 0x40000 |
| /psci method | 带 NUL 字符串 | smc |
| CPU device_type | 带 NUL 字符串，4 字节 | cpu |
| CPU reg | 不能复制源 8 字节；消费方读取本机序 uint32 | 源数值 0x0、0x100…0x700；仍须核对 ml_get_cpu_number 与启动 MPIDR 的语义 |

GIC 转换候选值满足当前 mapGic 的区域长度和总线范围条件。该静态判断不验证 MMIO 可访问性。

## 暂缓项

- 不生成最终 CPU 节点，直到逻辑编号/MPIDR 的消费链核对完成；不启用 sheng-smp。
- 不用 Linux memory/reg 直接替代 UEFI 分配表。
- 不将历史 high-RAM 数据载荷、哈希或预留窗口自动沿用为本机配置。
- NVRAM、根节点、chosen、defaults、DarwinBoot 交接仍需整体验证；上述属性集合不是完整 ADT。

## 内存对照的具体待核查项

1. 旧 XBL_Ramdump 在 0x84800000；当前同址是 qlink_logging，当前 xbl_ramdump 在 0x84A00000。需验证当前固件 xbl_config，而不是直接改地址。
2. 当前 ramoops 为 [0xA7000000, 0xA7400000)，与旧 FD_Reserved 和 UEFI_FD 重叠。需确认启动阶段的所有权转换与日志保留策略。
3. high-RAM 静态窗口 [0x8C0000000, 0xBEA400000) 落在两段相邻 Linux memory 区域的并集中；这只是范围覆盖，动态池和启动时占用尚未排除。
4. 15 个 reserved-memory 节点无 reg；不能从节点名或 size 推定实际分配地址。另有 2 个零长度 demura reg。

现阶段结论：可以继续离线开发转换器和验证器；尚无依据将旧内存表作为已验证的本机启动布局。
