# XNU 12377 CPU 拓扑核对

## 来源与边界

构建脚本固定 Apple XNU 提交 `ac9718fb1af618d5ce8678d0dc6e8a58f252216f`（xnu-12377.121.6）。本轮通过 GitHub 读取该提交的 [machine_routines.c](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/osfmk/arm64/machine_routines.c)，并核对本地 patches/xnu-12377。该目录涉及 machine_routines.c 的补丁只修改虚拟计时器路径，未修改本轮所读拓扑函数。未重新编译或验证完整预处理结果。

## 已确认规则

- ml_is_boot_cpu 必须读到 CPU `state` 属性，否则 panic。`running` 被识别为启动核。
- ml_parse_cpu_topology 遍历 `/cpus` 的直接子节点，按接受顺序生成逻辑 cpu_id；reg 是必需的物理 ID。
- 不能把 Linux cpu-map、缓存等辅助节点原样放入 ADT `/cpus` 直接子节点列表。
- ml_get_cpu_number 将输入掩码为 AFF1/AFF0，再匹配 topology 中的 phys_id，返回逻辑序号或 -1。本机 0x0…0x700 不丢失有效位。
- 必须有且仅有一个被接受的 running CPU；当前固件交接时实际启动 MPIDR 尚无证据，不能因为 FDT 列出 cpu@0 就宣称它一定是启动核。
- cluster-type 缺省进入 SMP 类型；E/M/P 会改变拓扑分类。Linux 的性能组不能未经验证转换为 Apple cluster-type。
- 00-bcm2837-machine-config.patch 设置 MAX_CPU_CLUSTERS=1；native-smp-secondary.patch 将 MAX_CPUS 从 4 调到 8，并让 BCM2837 次核复位路径保留 MPIDR 低 16 位。8 核容量不等于本机 SMP 可用。

## 候选约束

保留 CPU affinity；显式设置 state；验证唯一启动核；过滤 Linux 辅助节点。最小启动阶段不启用 sheng-smp、不使用 E/M/P 分类。当前 JSON 仍然只包含属性编码候选，没有自动选择启动核。

## ADT 完整性剩余事项

ArmDTPlatform 检查 chosen/NVRAM、cpus、arm-io、defaults、options，但这只是平台驱动入口，不是完整 XNU 属性清单。还需核查 pexpert 初始化、IODTNVRAM 对 CHRP 内容的校验，以及 DRAM 属性和 BootArgs 的关系。

已完成的是源码约束核对；未完成的是完整 ADT 校验、实际启动 MPIDR、UEFI 内存图与 GOP/EL1 交接验证。
