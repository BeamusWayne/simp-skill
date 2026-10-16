# v1 → v2 迁移与恢复

当前开发版本不自动迁移已有档案。保留 v1 checkout/安装副本后对选定档案操作。旧 meta.version 是备份版本，只有 schema_version 表示数据格式。

```sh
python tools/migrate_v2.py NAME --base-dir DIR
python tools/migrate_v2.py NAME --apply --expected-fingerprint PREVIEW_FINGERPRINT --base-dir DIR
python tools/migrate_v2.py NAME --check --base-dir DIR
```

默认预览只读，列出文件哈希、来源格式、损坏 JSONL 行与转换政策。源文件在预览后改变会使带指纹的 apply 拒绝继续；重新预览后使用新指纹。缺少 meta 可视为旧档案；损坏 meta 或未来 schema 拒绝转换并保留原文。

apply 获得档案锁，先建立完整恢复点并校验备份，再设置迁移标记。逐个归档旧逻辑文件到 legacy/v1；原始 memories 保留原位。新记录在内存构造并验证，以原子文件替换提交日志及投影，全部完成才移除标记。任何提交边界中断都保持“待恢复”状态；不存在无标记的半迁移可用档案。

旧判断、分数、阶段、画像、建议及缺少可靠归属的旧互动均保留为 legacy_record，损坏行也保留原文并列入问题清单。不会由分数换算新结论，不把旧互动自动算作已确认事件。重新导入原始聊天或由用户确认后，才新增 observation/user_report 等新类型。

`--check` 校验权威记录、依赖、投影一致性及引用文件的 SHA-256。再次 apply 完成的 v2 档案返回 already_v2，不生成重复记录；它不替代 check。

## 中断恢复

```sh
# 迁移中断：先完整恢复迁移前状态，再重新预览/应用
python tools/migrate_v2.py NAME --recover --base-dir DIR
# 普通追加已写日志、但投影未完成
python tools/memory.py rebuild NAME --base-dir DIR
# 完整备份恢复中断：继续恢复同一精确检查点
python tools/skill_writer.py --action recover-restore --slug NAME --base-dir DIR
```

恢复操作会先保留当前/部分状态，按清单恢复整组文件并逐个核验。恢复中再次中断可再次执行相应恢复命令。不要手动删除维护标记绕过校验。锁由操作系统持有，崩溃后释放；`.lock` 文件本身保留是正常情况。

## 完整备份及回退

```sh
python tools/skill_writer.py --action backup --slug NAME --base-dir DIR
python tools/skill_writer.py --action versions --slug NAME --base-dir DIR
python tools/skill_writer.py --action rollback --slug NAME --version EXACT_BACKUP_ID --base-dir DIR
```

备份覆盖日志、身份、互动索引、投影、旧档案、快照和 memories。versions 与运行中的维护标记不递归备份。rollback 先保存当前完整状态，再恢复指定检查点；恢复后不保留该检查点之外的新活动文件，但它们仍可从恢复前备份取回。精确 ID 必填，不接受前缀。

迁移前备份是 v1 格式，回退后使用旧版工具；v2 正常入口会要求迁移。这是完整回退，不混用旧投影和新日志。旧版没有清单的备份暂不支持由新版自动恢复。

旧 --score/--stage 明确报错且不写入；用户关系描述请写为有来源的 user_report。--golden 仅为源时间活跃小时统计别名，--milestones 仅为实际行动与结果，取消自动阶段推进。

本地文件锁仅协调本工具的操作。外部编辑器不会遵循它；不要在迁移/恢复时同时修改材料。路径拒绝越出档案以及符号链接/目录联接。完整备份包含原始材料，空间需求随档案增大。
