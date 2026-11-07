# 目标设备现状基线（只读采集）

日期：2026-11-08。采集方式：`adb` 只读查询，未写设备、未重启、未改权限。设备序列号不入库。

## 一、设备与系统

| 项目 | 值 |
| --- | --- |
| 型号代号 | `houji` |
| 型号 | 23127PN0CC（小米 14） |
| SoC | SM8650 / `qcom` |
| 系统 | 澎湃OS，Android 17 |
| 版本号 | `OS4.0.18.0.XNCCNXM`（`CP2A.260605.016`） |
| 构建类型 | `user` |
| 当前槽位 | `_a` |
| MemTotal | 15524336 kB（约 14.8 GiB） |

## 二、解锁与 root

| 项目 | 值 | 含义 |
| --- | --- | --- |
| `ro.boot.flash.locked` | `0` | Bootloader 已解锁 |
| `ro.boot.verifiedbootstate` | `orange` | AVB 处于解锁/自定义状态 |
| ADB shell 身份 | `uid=2000(shell)`，`u:r:shell:s0` | 默认非 root |
| `su -c id` | `uid=0(root)`，`u:r:ksu:s0` | KernelSU root 可用 |

解锁状态意味着 AVB 不会以签名不匹配为由拒绝自定义引导镜像，但**厂商是否允许 `fastboot boot` 命令本身仍需实测**。同机型先例（原作者设备）显示可用，本机尚未验证。

## 三、分区布局（关键项）

共 129 个 by-name 条目。以下为与项目相关的部分：

| 分区 | 设备节点 | 容量 |
| --- | --- | --- |
| 主 UFS LUN | `sda` | 490.7 GiB |
| `super`（动态分区） | `sda32` | 7.8 GiB |
| `userdata` | `sda33` | 482.0 GiB |
| `misc` | `sda11` | 4 MiB |
| `logfs` | `sda13` | 8 MiB |
| `boot_a` | `sde12` | 96 MiB |
| `init_boot_a` | `sde27` | 8 MiB |
| `vendor_boot_a` | `sde22` | — |
| `dtbo_a` | `sde16` | 24 MiB |
| `vbmeta_a` | `sde15` | 128 KiB |
| `recovery_a` | `sde25` | 独立 recovery 分区 |
| `persist` | `sdf7` | — |

**`cust` 分区不存在。** 这一点直接排除了「借用厂商分区放根卷」的方案。

## 四、存储余量

`/data` 为 f2fs，经 dm-linear 映射（`dm-49`）挂载：

| 项目 | 值 |
| --- | --- |
| 总容量 | 482 GiB |
| 已用 | 173 GiB |
| 可用 | 309 GiB |

按 houji iOS 16 移植的 32 GiB 系统卷估算，容量不是瓶颈。

## 五、对项目路线的直接影响

1. **P4 根卷方案收窄为两条**：外接 USB 存储，或 userdata 内文件。原方案 D（借用现有分区）因 `cust` 不存在而排除；方案 E（缩小 userdata 重划分）违反禁止清单。
2. **容量充足**：309 GiB 空闲，放得下 32 GiB 系统卷。真正的障碍不是空间，是 XNU 需要以块级方式访问这段空间，而 `/data` 是 f2fs 上的文件。
3. **`misc` 仅 4 MiB**：bootcontrol 与 bootcount 都在这里，指纹必须覆盖。
4. **存在独立 `recovery_a`**：安装 OrangeFox 之类会改写该分区，属禁止清单范围。恢复不依赖自定义 recovery。

## 六、指纹基线

已采集并保存于仓库外私有目录 `fingerprint-before.json`：

| 对象 | SHA256 前 16 位 | 大小 |
| --- | --- | --- |
| `misc` | `f4d714ba77ad6168` | 4.0 MiB |
| `boot_a` | `9b8fc3be39843bc2` | 96.0 MiB |
| `vbmeta_a` | `47a206e141ae662e` | 128 KiB |
| `dtbo_a` | `a73b91098e2cc1f5` | 24.0 MiB |
| `init_boot_a` | `ddbf8e8e04b075ce` | 8.0 MiB |
| 分区清单 | `fb018ac48709a86a` | — |
| `/proc/partitions` | `94e0e85d245828c7` | — |

这份基线是首轮实机启动后的比对基准。任何一项变化都说明发生了预期外的持久写入。

## 七、采集边界

- 未读取任何分区内容到报告（只记录哈希）。
- 未写设备、未改权限、未挂载、未重启。
- `misc` 的 4 MiB 全量读取已完成；`boot_a` 96 MiB 全量读取已完成。
- 未验证 `fastboot boot` 可用性——需要重启进 bootloader，等有镜像时一次做完。
