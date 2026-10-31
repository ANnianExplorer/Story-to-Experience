# 新功能最小文档模板

本文件是模板，不是现行需求。复制后分成 SPEC 与 SDD 两份，登记 feature-registry.json。

## SPEC 必填

目标/非目标；稳定需求 ID；角色/权限；输入输出；错误/取消/重试；状态机；兼容迁移；每项需求对应正向、负向与必要竞争验收；完成边界。公共字段链接权威契约，不再写镜像。

## SDD 必填

关联 SPEC/ADR；五层落点与数据所有权；主链路；端口与事务；异常恢复；任务 ID/需求/依赖/允许路径/DoD；测试策略；回退。

## 登记与状态

初始 design=draft、implementation=planned、implementation_paths/evidence 为空。完成基线后才 design=baseline。实现路径与实际报告登记后再按工作流升级；不能预填已验证。

