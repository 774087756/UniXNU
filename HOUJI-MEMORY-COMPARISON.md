# UEFI / live FDT range comparison

FDT SHA256: `447f252737e719c110495b0b9100d2aac8783265a862f35dd6ae80f820f22ddd`
MemoryMapLib SHA256: `4f6f19b992fd647f425a4cf5db52da9f7ad2d178d1463143897f609dc53df89f`

Address intersections only: overlaps are not automatically bugs. Linux and UEFI use different lifecycle allocations. No overlap is not proof of safety.

| UEFI entry | Start | Size | Intersecting fixed FDT reservations |
| --- | --- | --- | --- |
| RSRV0 | 0x816e0000 | 0x320000 | dump_display_region@816e0000 |
| XBL_DT | 0x81a00000 | 0x40000 | xbl_dtlog_region@81a00000 |
| Minidump_Regions | 0x81bff000 | 0x1000 | xbl_md_region@81bff000 |
| AOP | 0x81c00000 | 0xa0000 | xbl_aop_image_region@81c00000, aop_cmd_db_region@81c60000, aop_tme_uefi_merged_region@81c80000 |
| UEFI_Log | 0x81ce4000 | 0x10000 | aop_tme_uefi_merged_region@81c80000 |
| SMEM | 0x81d00000 | 0x200000 | smem_region@81d00000 |
| PvmFw | 0x824a0000 | 0x100000 | pvmfw_region@0x824a0000 |
| XBL_Ramdump | 0x84800000 | 0x200000 | qlink_logging_region@84800000 |
| PIL_Reserved | 0x8bc00000 | 0x16f80000 | mpss_region@8bc00000, q6_mpss_dtb_region@9b000000, ipa_fw_region@9b080000, ipa_gsi_region@9b090000, gpu_microcode_region@9b09a000, lost_reg_mem, spss_region_region@9b0a0000, spu_secure_shared_memory_region@9b280000, spu_secure_shared_memory_region@9b2e0000, camera_region@9b300000, video_region@9bb00000, cvp_region@9c300000, cdsp_region@9ca00000, q6_cdsp_dtb_region@9de00000, q6_adsp_dtb_region@9de80000, adspslpi_region@9df00000 |
| Display_Demura | 0xa3600000 | 0x2b00000 | none |
| FD_Reserved | 0xa7000000 | 0x100000 | ramoops_region |
| UEFI_FD | 0xa7100000 | 0x300000 | ramoops_region |
| UEFI_FD_Reserved | 0xa7400000 | 0x200000 | none |
| CPU_Vectors | 0xa7600000 | 0x1000 | none |
| Info_Blk | 0xa7601000 | 0x1000 | none |
| MMU_PageTables | 0xa7602000 | 0x3000 | none |
| Log_Buffer | 0xa7605000 | 0x8000 | none |
| UEFI_Stack | 0xa760d000 | 0x40000 | none |
| SEC_Heap | 0xa764d000 | 0x8c000 | none |
| Sched_Heap | 0xa76d9000 | 0x400000 | none |
| FV_Region | 0xa7ad9000 | 0x400000 | none |
| UEFI_RESV | 0xa7ed9000 | 0x127000 | none |
| Kernel | 0xa8000000 | 0x10000000 | none |
| DXE_Heap | 0xb8000000 | 0x1ba00000 | none |
| TZApps_Reserved | 0xd8800000 | 0x1b000000 | none |
| Display_Reserved | 0xfc400000 | 0x2b00000 | splash_region |

## Linux memory tuples

| Start | Size | End (exclusive) |
| --- | --- | --- |
| 0x816e0800 | 0x31f800 | 0x81a00000 |
| 0x81a40000 | 0x1bf000 | 0x81bff000 |
| 0x81cf5000 | 0xb000 | 0x81d00000 |
| 0x81f20000 | 0x580000 | 0x824a0000 |
| 0xd8800000 | 0x0 | 0xd8800000 |
| 0xe7830000 | 0x178d0000 | 0xff100000 |
| 0xff3dd000 | 0x423000 | 0xff800000 |
| 0xffe00000 | 0x200000 | 0x100000000 |
| 0x880000000 | 0x2f700000 | 0x8af700000 |
| 0x8b0000000 | 0x5f00000 | 0x8b5f00000 |
| 0xa00000000 | 0x200000000 | 0xc00000000 |
| 0x8c0000000 | 0x140000000 | 0xa00000000 |
| 0x8b6100000 | 0x1e00000 | 0x8b7f00000 |
| 0x82800000 | 0x2000000 | 0x84800000 |
| 0x84c00000 | 0x1f00000 | 0x86b00000 |
| 0xa2580000 | 0x35a80000 | 0xd8000000 |

## Reservations without fixed reg

- /reserved-memory/qseecom_region
- /reserved-memory/qseecom_ta_region
- /reserved-memory/qmc_dma_region
- /reserved-memory/non_secure_display_region
- /reserved-memory/vm_comm_mem_region
- /reserved-memory/oem_vm_region@f7c00000
- /reserved-memory/va_md_mem_region
- /reserved-memory/sp_region
- /reserved-memory/cdsp_eva_region
- /reserved-memory/adsp_heap_region
- /reserved-memory/linux,cma
- /reserved-memory/secure_cdsp_region
- /reserved-memory/debug_kinfo_region
- /reserved-memory/mem_dump_region
- /reserved-memory/cnss_wlan_region

Symbolic UEFI high-RAM entry is excluded from the literal table and requires separate review of HoujiRootRAM.h. Dynamic reservation addresses cannot be inferred from size. This report does not authorize allocations or boot.
