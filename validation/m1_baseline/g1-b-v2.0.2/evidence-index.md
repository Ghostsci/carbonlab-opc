# Evidence Index

> PREPARATION_ONLY / every command is expected to exit 0; SHA-256 is resolved through `manifest.json`.

| acceptance | evidence path | command | expected exit | evidence SHA-256 |
|---|---|---|---:|---|
| 指定来源 SHA/tree/clean | `provenance/source-baseline.json` | `python3 generator/generate.py --verify .` | 0 | `e4ddf056439dff8ee0f8a07a17f613301ca6e2d359228ecbf1de18ea65cbeca4` |
| 精确规则归档 19/19 与批准链 | `provenance/rule-baseline-verification.json` | `python3 generator/generate.py --verify .` | 0 | `b1f01d64011b020e1731b18dd635eb986ed001fce9d3fcf3d936e13ddec6975b` |
| 39/39 字段、单位、期间、证据、排放、强度与状态 | `verification/verification-report.json` | `python3 generator/generate.py --verify .` | 0 | `92f20d67ad4f7957bb5434bfc6b494e96d465909b5c6b8b27d5db87d8261c031` |
| 51/51 受控文件哈希 | `hashes.md` | `python3 generator/generate.py --verify .` | 0 | `6125b1b7920eff2b9e84c208c1b917acf40d103acb12c1d3c82289cf577bf47b` |
| manifest/dataset/self hash | `manifest.json` | `python3 generator/generate.py --verify .` | 0 | `SEE_manifest_self_sha256_IN_manifest.json` |
| 两次隔离重放 | `verification/replay-attestation.json` | `./scripts/replay_g1_b_v2.sh OUT` | 0 | `2681d1fbce1b76d651dd65140da6bacb2bf3aa70a5dbc4d25ff2798d7fc81e7c` |
| legacy 逐案例/逐文件差异 | `legacy-comparison/legacy-to-v2-diff.md` | `python3 generator/generate.py --verify .` | 0 | `a6a5555a4eeb77db3fc8ad4603d478c0fe47ca9a1f8cfcc538307a611eb1fd40` |
| withdrawn v2.0.0 → v2.0.2 39 条机器差异 | `legacy-comparison/withdrawn-v2.0.0-result-diff.json` | `python3 generator/generate.py --verify .` | 0 | `c6a8ae56ade16a1e02217301b53b36978ee4f2255046de997600d1da9e3427df` |
| 51 项旧登记映射 | `legacy-comparison/legacy-51-map.json` | `python3 generator/generate.py --verify .` | 0 | `5ce636218c770c1628e5c1beda3847af95d9f5cce76d05a41d4425b46f7a9688` |
| ACL deny/QA 最小授权/隔离/审计 | `access/access-test-report.json` | `python3 generator/generate.py --verify .` | 0 | `0728e9e79c7b9cdd6c5900294326dd316de56333c6a2d79887030362d350680f` |
| split/access 实施范围与退出码 | `access/control-implementation-evidence.json` | `python3 generator/generate.py --verify .` | 0 | `1b896895bd893c7adc33f00f8f5456365a68a4a4fc9f204176aff9640361e3c7` |
| 开发制品 truth 泄漏检查 | `access/leakage-check.json` | `python3 generator/generate.py --verify .` | 0 | `0b5974c65d94f1f51d12955365f9a3affb3d6220f603c71a6dbf2437842ce90d` |
