# CHRP NVRAM 离线核对

核查来源为 Apple XNU 固定提交 ac9718fb1af618d5ce8678d0dc6e8a58f252216f：

- [IONVRAM.cpp](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/iokit/Kernel/IONVRAM.cpp)
- [IONVRAMCHRPHandler.cpp](https://github.com/apple-oss-distributions/xnu/blob/ac9718fb1af618d5ce8678d0dc6e8a58f252216f/iokit/Kernel/IONVRAMCHRPHandler.cpp)

## 消费规则

IODTNVRAM::initImageFormat 从 chosen 读取 nvram-bank-size 与 nvram-proxy-data。CHRP init 要求传入长度与 bank size 一致；unserializeImage 对整个 bank 的 Adler 校验失败会 panic。v1/v2 的 Adler 覆盖从 generation 字段（偏移20）到 bank 末尾。CHRP 头为16字节，len 单位是16字节块。

这解释了为什么 ArmDTPlatform 仅检查属性存在及宽度还不够。离线检查须额外验证实际数据长度、完整分区范围、头部和 Adler 校验。

## 本次测试

check-houji-chrp.py 从历史 make-houji-adt.py 中单独提取 nvram_proxy 函数执行，不运行其 main、不调用外部参考生成器、不读取手机。

| 分区 | 起始偏移 | 总长度 |
| --- | --- | --- |
| nvram | 0 | 32 |
| common | 32 | 2064 |
| free | 2096 | 6096 |

总长度8192字节，校验通过。四个负例均被拒绝：头部校验字节损坏、Adler 字段损坏、bank 内容损坏、重新计算校验和后的分区越界。

本工具是限定于该空白 v1 fixture 的保守校验模型，不是通用 NVRAM parser，也没有编译或执行 Apple 的实际处理器。历史空白 bank 可以保留为候选；不能宣称 NVRAM 服务已实机工作，更不涉及手机持久 NVRAM 写入。

## 内存属性核查状态

同提交 pexpert/arm/pe_init.c 和 osfmk/arm64/arm_vm_init.c 已读取，未发现 dram-base/dram-size 字符串。这个局部搜索不证明全内核不消费这些属性。当前 DarwinBoot 通过 BootArgs 填入窗口大小已确认；完整 ADT 的 DRAM 字段策略仍未定案。

剩余：getNVRAMProperties 的属性来源和默认值、变量反序列化和发布过程、完整 ADT 解析校验，以及最终启动时的实际运行验证。
