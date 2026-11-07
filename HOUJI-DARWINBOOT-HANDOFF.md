# CPU 与 DarwinBoot 交接核对

## 已确认的 CPU 消费链

当前 ArmCpu.cpp：probe 读取 reg 前 4 字节作为物理 ID；start 将该值传给 ml_get_cpu_number，并将原值保留为 affinity / info.phys_id。startCPU 使用 affinity 构造 PSCI CPU_ON 参数。

因此候选 reg 必须保留 0x0、0x100…0x700 这些 affinity 数值，不能改成顺序编号 0…7。应由大端 64 位解码，检查能否容纳于当前 ABI，再编码为小端 32 位。

本地尚未定位到本次构建 XNU 的 ml_get_cpu_number 实现，不能断言逻辑拓扑已验证。启动 CPU 的实际 MPIDR 也未采集。HOUJI-ADT-CANDIDATE.json 只记录候选属性，不输出最终 CPU 拓扑或可启动 ADT。

## 当前 DarwinBoot 实现

来源：drivers/DarwinBoot/DarwinBootPkg/Driver/DarwinBoot.c 和 WindowSize.h。

- Boot 要求 CurrentEL 原始值为 4，即 EL1；非零 KextCount 和直接传入 DeviceTree 被拒绝。树从内核文件路径加 `.adt` 读取。
- 窗口默认 256 MiB；显式值要求 256 MiB 至 8 GiB 且 2 MiB 对齐。这是解析边界，不是可分配容量。
- AllocateWindow 只从实际 UEFI EfiConventionalMemory 中寻找窗口；可合并相邻描述符，最终仍须 AllocatePages(AllocateAddress, EfiLoaderCode) 成功。
- 内核段、BootArgs、ADT、可选 ramdisk/trustcache 均在已申请窗口中安排，并检查 Used 不超过 WindowSize-BLOCK_SIZE。
- BootArgs 的 PhysicalBase、MemorySize、MemorySizeActual、TopOfKernelData 来自本次分配。当前所读 Boot 路径未自动重写 ADT 的 dram-base/size，不能把旧生成器占位值的处理方式套用过来。
- ReadBootVideo 在分配前执行，失败则终止；GOP 仍是前置条件，不能仅凭 splash 保留地址认为图形交接完成。
- 最后重新获取 UEFI memory map key 后 ExitBootServices，成功才 DarwinEnter。进入这个阶段后的失败路径可能 CpuDeadLoop，不能承诺自动返回 Android。

## 本轮交付与验证范围

prepare-houji-adt-contract.py 从指定本机 FDT 生成离线 JSON。验证 cell 宽度、唯一 GIC、PSCI method、GIC 总线边界、stride、CPU 数值宽度及唯一性。对本机输入生成成功，GIC/CPU 输出反解正确；截断和无效头输入被拒绝。

这不是完整 ADT 序列化器，没有执行 UEFI 分配、内核或手机 MMIO。本轮不改驱动/固件内存地址。

下一步：取得与 CI 同提交及补丁一致的 XNU 拓扑实现，核对 CPU 节点属性；核查完整 chosen/NVRAM/DRAM 属性消费路径，再实现完整离线 ADT 校验。
