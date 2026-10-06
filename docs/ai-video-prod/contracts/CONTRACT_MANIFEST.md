# AI 广告视频自动生产系统｜Canonical Contract Manifest

**Package Status: COMPLETE**
**Package Date: 2026-08-11**

## Canonical Priority
```text
L1 > L2 > L3 > L4 > Implementation Notes > Existing Code Behavior
```

## Required Core Files
- `L1_Product_and_Scope_Contract_v1.0.md`
- `L2_Production_Contract_v1.0.md`
- `L3_Domain_Model_and_System_Architecture_Contract_v1.0.md`
- `L4_Production_Acceptance_Contract_v1.3.md`
- `Codex_Master_Execution_Prompt_v1.1.md`

## Integrity Rule

Codex 启动时必须先验证所有核心文件存在并校验 SHA-256。

缺任何核心文件：
```text
CONTRACT_PACKAGE_INCOMPLETE
```

不得把“文档引用了该合同”视为“合同文件存在”。

## SHA-256
```text
44976510326245aaed2c9274d15db85d36ae77f6056762bf13e2942d0b5158e3  L1_Product_and_Scope_Contract_v1.0.md
ba9ea7e30b04da614795c88fc55e0a674a025baacbe5a306d8494fd2efafa304  L2_Production_Contract_v1.0.md
a9c1f7d9c52a7cd5701e0ad4d669d9340e86154716c727e923f133bf4e04134e  L3_Domain_Model_and_System_Architecture_Contract_v1.0.md
bc7c5cc593bcaa356e9b88727332cd0bb6c4adff1150045c013e5520930b7a46  L4_Production_Acceptance_Contract_v1.3.md
f0562ee655ebc5231db243aed4ac2be1a0c1f707bd7d3c06600bf31e3267b021  Codex_Master_Execution_Prompt_v1.1.md
```

## Load Order
```text
CONTRACT_MANIFEST
→ L1
→ L2
→ L3
→ L4
→ Codex Master Execution Prompt
→ Current Project Checkpoint
```
