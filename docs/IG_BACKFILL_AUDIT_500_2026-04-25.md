# IG Backfill Audit 500 2026-04-25

## Scope

- Workspace: `bac7ce63-e768-454d-96f3-3a00e8e1df69`
- Population: latest `500` completed refs from live `ig_reference_catalog`
- Audit artifacts:
  - `/tmp/ig_recent500.tsv`
  - `/tmp/ig_recent500_audit.json`
  - `/tmp/ig_recent500_audit.csv`

## Summary

- `sample_size` = `500`
- `clean_count` = `204`
- `token_pollution_count` = `6`
- `field_collapse_count` = `272`
- `mixed_count` = `18`
- `read_errors` = `0`

## Raw Pattern Counts

- `construct_or_assemble_json` = `258`
- `output_only_json` = `152`
- `top_level_json_start` = `403`
- `visual_analysis_heading` = `119`
- `return_only_structure` = `50`
- `json_structure_check` = `23`

## 500-Row Audit Table

| # | Shortcode | Ref ID | Handle | Audit Status | Strategy | Evidence | |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `DLpGLCqpLVI` | `ref_0861abdf` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 2 | `DMubr4tywix` | `ref_4d0ac26b` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like phone camera)'] | |
| 3 | `DMw6bNJyfwN` | `ref_41093555` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=16-18 or 19-22. Looks young adult. Let's say 19-22.; clothing_generic_garment=Black top, black long sleeves, black boots.; coverage_notes_key_leak=upper_body_coverage: partially_covered (top is sho... | |
| 4 | `DM2ECu4yAhs` | `ref_175861db` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Kimono (modified), Fur collar, Lace gloves. | |
| 5 | `DNXUpTRStKO` | `ref_5c0227f9` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera, maybe 50mm equivalent or slightly wider)', 'focal_length_class: "standard" (looks like phone portrait mode)'] | |
| 6 | `DNaKvI1BlmM` | `ref_ad5f4ae4` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like a phone or small camera, maybe 50mm equivalent)'] | |
| 7 | `DNkkwYRyTrn` | `ref_96e23441` | `@university.tw` | `clean` | `no_action` |  | |
| 8 | `DO-LSg2Er59` | `ref_d541ad9a` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "standard" or "short-telephoto" (looks like a phone portrait mode)', 'focal_length_class: standard (looks like phone portrait)', '* weather_atmosphere: "clear" or "overca... | |
| 9 | `DPNh8tVkmep` | `ref_59ab7ffb` | `@university.tw` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=['{']; materials_inline_literal_collapse | |
| 10 | `DPQwBMJkmah` | `ref_b5612d48` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" or "short-telephoto" (looks like phone portrait mode or 50mm)'] | |
| 11 | `DPTLeQMEi3A` | `ref_d717de0a` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['coverage: Upper body is partially covered (off shoulder)', 'focal_length_class: standard (looks like 50mm equivalent or slightly wider)'] | |
| 12 | `CQXgrf7jzPy` | `ref_59734348` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 13 | `CQaes1Xj_2B` | `ref_8a49d757` | `@chiushan_x` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | environment_foreground=['texture']; materials_inline_literal_collapse | |
| 14 | `CRYsuNXLZFb` | `ref_90c06d75` | `@chiushan_x` | `clean` | `no_action` |  | |
| 15 | `CSMa4xaLAP_` | `ref_bb2222b6` | `@chiushan_x` | `clean` | `no_action` |  | |
| 16 | `CSo4gobhzaJ` | `ref_79c355fc` | `@chiushan_x` | `clean` | `no_action` |  | |
| 17 | `CSq970SBJlc` | `ref_06d46806` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 18 | `CUUaHJuLqFz` | `ref_fd8615b8` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 19 | `CbfFBPfrrPG` | `ref_7389aec4` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "standard" (Looks like phone camera, maybe 50mm equiv or slightly wider)'] | |
| 20 | `CbsMXTMrpQS` | `ref_32ed5b9d` | `@chiushan_x` | `clean` | `no_action` |  | |
| 21 | `CcLID4Ghr7Y` | `ref_60dff553` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (Portrait shot, likely 50mm equivalent)'] | |
| 22 | `CcvDd4-LHq_` | `ref_04cf85c5` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 23 | `CgbdIgwLYvb` | `ref_dd89ed3a` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 24 | `CibnZV0LSeO` | `ref_549d855e` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 25 | `CnJ4X7ILXo9` | `ref_595b8570` | `@chiushan_x` | `clean` | `no_action` |  | |
| 26 | `Co_vT7Srkl7` | `ref_435d34b5` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "short-telephoto" or "standard" (looks like phone portrait mode or 50mm equivalent)', 'focal_length_class: standard (looks like portrai... | |
| 27 | `CpXn9dNL-w1` | `ref_c406623f` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* *focal_length_class:* standard (looks like a portrait shot)'] | |
| 28 | `CqkYCmELlWl` | `ref_e69a5ed3` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone camera)', 'weather_atmosphere: unknown (looks clear but filter obscures)'] | |
| 29 | `CsGXfL2rFir` | `ref_5ed09048` | `@chiushan_x` | `clean` | `no_action` |  | |
| 30 | `CsLvsGRy1cj` | `ref_1c668eb3` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like portrait shot)'] | |
| 31 | `CujQmtbru01` | `ref_31b794f5` | `@chiushan_x` | `clean` | `no_action` |  | |
| 32 | `Cvcnr3ZLGeN` | `ref_0bcdc192` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 33 | `CwNcSGLLUk3` | `ref_095b8d54` | `@chiushan_x` | `clean` | `no_action` |  | |
| 34 | `CwkCFEzreze` | `ref_696d8c7b` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 35 | `CyFh3Z3L2vg` | `ref_f17e17f8` | `@chiushan_x` | `clean` | `no_action` |  | |
| 36 | `CzGrik6y0aJ` | `ref_fa2dc817` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like phone camera)'] | |
| 37 | `CzZKliOBozy` | `ref_6f93d01c` | `@chiushan_x` | `clean` | `no_action` |  | |
| 38 | `C0E_wQSh_nz` | `ref_c379fab0` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=white top, straps on chair. | |
| 39 | `C1eb82Hr2Cg` | `ref_c71cf021` | `@chiushan_x` | `clean` | `no_action` |  | |
| 40 | `C4Ku57ILEqf` | `ref_b806c78e` | `@chiushan_x` | `clean` | `no_action` |  | |
| 41 | `C4k2OW4STB9` | `ref_43ac1be7` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 42 | `C50hxj2PqkZ` | `ref_7df2f0bb` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 43 | `C8e1oGvpQG5` | `ref_836daff1` | `@chiushan_x` | `clean` | `no_action` |  | |
| 44 | `C_IPXIGvIaj` | `ref_c5a6f6bc` | `@chiushan_x` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* coverage: {"upper_body_coverage": "covered", "lower_body_coverage": "covered", "chest_visibility": "covered", "chest_c', '* coverage: upper "covered", lower "covered", chest "covered"', '* f... | |
| 45 | `DJH2MKMo4V0` | `ref_eeeba7bf` | `@yun_qing.me` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone camera)', 'weather_atmosphere: unknown (plants look green, maybe overcast)'] | |
| 46 | `DKcST3boQD5` | `ref_febfb24e` | `@yun_qing.me` | `clean` | `no_action` |  | |
| 47 | `DMmfDYZRRQe` | `ref_71901d98` | `@yun_qing.me` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "short-telephoto" or "standard" (looks like a phone camera or small lens)'] | |
| 48 | `DOL8RLHDBtj` | `ref_7464baf4` | `@yun_qing.me` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 49 | `DO_shh5DMtT` | `ref_e90164e4` | `@yun_qing.me` | `clean` | `no_action` |  | |
| 50 | `DPBNlLCjN_C` | `ref_1ae884be` | `@yun_qing.me` | `clean` | `no_action` |  | |
| 51 | `DQzh37zDDnL` | `ref_8914d54e` | `@yun_qing.me` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (likely phone or small camera)'] | |
| 52 | `DQzh7lkjGZM` | `ref_91a3b7c3` | `@yun_qing.me` | `clean` | `no_action` |  | |
| 53 | `DSW76mJDLN5` | `ref_668294f6` | `@yun_qing.me` | `clean` | `no_action` |  | |
| 54 | `DSdBAN1DFxE` | `ref_5587a721` | `@yun_qing.me` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or wide (looks like a phone camera, maybe slightly wide)', 'focal_length_class: "standard" (looks like phone camera)', 'weather_atmosphere: unknown (looks clear bu... | |
| 55 | `DTyYkz9DKLa` | `ref_b24732f6` | `@yun_qing.me` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or wide (looks like a phone or small camera)'] | |
| 56 | `DTyYpFIjLH2` | `ref_9780db2a` | `@yun_qing.me` | `clean` | `no_action` |  | |
| 57 | `DPibeWLEi2I` | `ref_24991685` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like 50mm equivalent)'] | |
| 58 | `DQGvbhuEqco` | `ref_8f9d447e` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 59 | `DQTQxTyEnj6` | `ref_3d755244` | `@university.tw` | `clean` | `no_action` |  | |
| 60 | `DQYrte1Adh1` | `ref_e54f123f` | `@university.tw` | `clean` | `no_action` |  | |
| 61 | `DOdl2UHCG4T` | `ref_e090e725` | `@sujistrashcan` | `clean` | `no_action` |  | |
| 62 | `DUp3v_5Eu-A` | `ref_216416c5` | `@sujistrashcan` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | materials={'material_type': 'material_type'}; materials_inline_literal_collapse | |
| 63 | `DQtM2wmkjO8` | `ref_b57bb7a3` | `@university.tw` | `clean` | `no_action` |  | |
| 64 | `DQv1pAOEouJ` | `ref_624f2af0` | `@university.tw` | `clean` | `no_action` |  | |
| 65 | `DRJnP4Bklsc` | `ref_bf39058f` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like phone camera, maybe 50mm equivalent)', 'focal_length_class: standard (looks like phone portrait mode)'] | |
| 66 | `DRMLbWXEr86` | `ref_05b39cb5` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=16-18 or 19-22 (looks young adult/teen). Let's go with 19-22 based on maturity. | |
| 67 | `DRg_jgZkuJG` | `ref_abc5715c` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=16-18 or 19-22. Looks young adult. Let's say 19-22. | |
| 68 | `DR_keFGkqT5` | `ref_f1d17a3d` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "standard" (looks like phone camera, maybe slightly wide)', '* weather_atmosphere: "clear" (sky not visible but lighting suggests)'] | |
| 69 | `DSj5gRRktEJ` | `ref_eed8126e` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=16-18 or 19-22. Looks young adult/late teen. Let's go with 19-22 based on maturity.; clothing_generic_garment=Black crop top, black skirt, olive green jacket, brown boots. | |
| 70 | `DSmeZoXEm6B` | `ref_e26cf450` | `@university.tw` | `clean` | `no_action` |  | |
| 71 | `DTSDHBMgTj5` | `ref_69928f88` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Sailor uniform (collar, ribbon), white shirt.; evidence_note_key_leak=['focal_length_class: standard (looks like 50mm or 85mm, portrait lens)'] | |
| 72 | `DTcf5_QkgmG` | `ref_208aa1d4` | `@university.tw` | `clean` | `no_action` |  | |
| 73 | `DThm2wyEirA` | `ref_dc289c81` | `@university.tw` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | materials={'material_type': 'material_type'}; materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22. Looks young, likely late teens or early 20s. Let's go with 19-22.; evidence_note_key_leak=['focal_le... | |
| 74 | `DTkDAUSErOj` | `ref_03533522` | `@university.tw` | `clean` | `no_action` |  | |
| 75 | `DTrzUS3kv-t` | `ref_a9eae05f` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=13-15" or "16-18". Looks young, youthful face. Let's say "13-15" or "16-18". Face looks young. Let's go with "13-15. | |
| 76 | `DTudDDBEkAB` | `ref_4ecf6760` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 77 | `DVc9F9PlESD` | `ref_eb5f9be6` | `@chengyang_shen` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone portrait mode)'] | |
| 78 | `DVn22g3lPTB` | `ref_f3c824c8` | `@chengyang_shen` | `clean` | `no_action` |  | |
| 79 | `DVpYCHGFJJ1` | `ref_8a7d5f02` | `@chengyang_shen` | `clean` | `no_action` |  | |
| 80 | `DVxzEZplUYu` | `ref_e0b6a78b` | `@chengyang_shen` | `clean` | `no_action` |  | |
| 81 | `DVx_22WlF0R` | `ref_63aedb7e` | `@chengyang_shen` | `clean` | `no_action` |  | |
| 82 | `DV7WYm6Cfk2` | `ref_ba65ce4f` | `@chengyang_shen` | `clean` | `no_action` |  | |
| 83 | `DV-4EoqlAr0` | `ref_24016413` | `@chengyang_shen` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* pose: stance: standing/sitting (hard to tell, likely standing), gesture: holding phone, gaze_direction: camera (lookin'] | |
| 84 | `DWGcRCFFbO2` | `ref_b52d667a` | `@chengyang_shen` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 85 | `DTrbhctlLR_` | `ref_9c6c077b` | `@chengyang_shen` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22 (looks young adult) -> 19-22; evidence_note_key_leak=['* focal_length_class: standard (looks like phone camera)'] | |
| 86 | `DUAc7N4ErDj` | `ref_30d50a79` | `@university.tw` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | materials={'material_type': 'material_type'}; materials_inline_literal_collapse; evidence_note_key_leak=['lower_body_coverage: partially_covered (dress covers upper legs, bare below)', 'focal_length_class: standard (l... | |
| 87 | `DUDByzPEkZn` | `ref_012f4830` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)'] | |
| 88 | `DUFneJCkpGN` | `ref_4d6a6648` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)', 'focal_length_class: "standard" (looks like phone)'] | |
| 89 | `DUH-QAWEvE4` | `ref_1fded5c0` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=White tank top, grey pinstripe trousers. | |
| 90 | `DUSl80HknZl` | `ref_396d716d` | `@university.tw` | `clean` | `no_action` |  | |
| 91 | `DUVHUYBEtnV` | `ref_92d7fd76` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)'] | |
| 92 | `DUXlUvYkme-` | `ref_782bfb35` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or small camera)'] | |
| 93 | `DUaKgoKku53` | `ref_797cf6cf` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard (looks like a portrait lens, maybe 50mm or 85mm equivalent)'] | |
| 94 | `DCwAUe4yIrz` | `ref_7f0907a6` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or short-telephoto (looks like a phone shot or small lens)'] | |
| 95 | `DCyrXmXSirO` | `ref_39e35918` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard / wide (looks like phone camera)'] | |
| 96 | `DC38apoy9Ng` | `ref_45c9a4ae` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 97 | `DC6QDwlSnub` | `ref_f3c28cb3` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or short-telephoto (looks like a phone camera or portrait mode)', 'focal_length_class: "standard" (looks like phone portrait mode)'] | |
| 98 | `DC81DKbyRIa` | `ref_53472ffb` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* coverage: {"upper_body_coverage": "partially_covered", "lower_body_coverage": "bare", "chest_visibility": "visible", "', '* focal_length_class: standard or short-telephoto (looks like phone ... | |
| 99 | `DDB5pZpy_v5` | `ref_af5f8436` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 100 | `DDHU6HbSnFB` | `ref_af468d0f` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 101 | `DDJw9L5S8Vq` | `ref_4352e891` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 102 | `DDZqWXvyVBY` | `ref_f38cd6db` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=19-22 or 23-29. Looks young adult. Let's say 20-25 range. Bucket 19-22 or 23-29. Features look youthful. Let's go with 1; clothing_generic_garment=Bikini top (cow print), Sarong (white).; evidence_... | |
| 103 | `DDa6tXEyPO_` | `ref_1cdf7a92` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a portrait shot, maybe 50mm equivalent or slightly wider due to perspective)'] | |
| 104 | `DDeSiuPSMFa` | `ref_ec2a974e` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22 (looks young adult/teen). Let's go with 16-18 or 19-22. Looks like late teens. | |
| 105 | `DDhYMowS1Is` | `ref_18ff4d21` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera, maybe 50mm equivalent or slightly wider)'] | |
| 106 | `DDj36q2yiIY` | `ref_035f070a` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "short-telephoto" (likely phone selfie lens)'] | |
| 107 | `DDlqz_zycBM` | `ref_657f9e05` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 108 | `DDpG8bTSqK5` | `ref_8dc2fc64` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 109 | `DDt-luFyEYV` | `ref_8b2beb09` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 110 | `DD1h0S6ScR9` | `ref_44093d62` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like phone camera)', '* focal_length_class: standard (looks like phone portrait mode)'] | |
| 111 | `DD4f8asSDf8` | `ref_12ab8293` | `@attractive_hotness_girls` | `token_pollution` | `reparse_raw_with_hardened_stop_lines_then_review_full_payload` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; environment_set_d... | |
| 112 | `DD9P2Ziy5bt` | `ref_3d2da782` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=White bra with lace trim.; evidence_note_key_leak=['focal_length_class: standard/short-telephoto (looks like a phone camera, maybe 50mm equivalent or less)', 'focal_length_class: short-telepho... | |
| 113 | `DEe72GwyFGg` | `ref_06953cea` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=19-22 or 23-29. Looks young adult. Let's say 19-22 based on skin texture and bone structure.; clothing_generic_garment=Black lace top, fishnet stockings, black wrist cuffs, silver chain necklace, b... | |
| 114 | `DEkFNN_SJSr` | `ref_dde997cf` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)'] | |
| 115 | `DEmxZoySnsy` | `ref_af113658` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 116 | `DFAHHzMSz-w` | `ref_616b2c26` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['coverage: Upper body covered by bikini top (bare chest otherwise)', 'focal_length_class: standard/short-telephoto (looks like a phone or small camera)'] | |
| 117 | `DSpaANQk7-b` | `ref_7a1b6f46` | `@mmarukoooo` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: medium or wide (looks like a wide shot of the room)'] | |
| 118 | `DSpwKYvkxy4` | `ref_4110aaf1` | `@mmarukoooo` | `clean` | `no_action` |  | |
| 119 | `DSzWHitkyM3` | `ref_e4af690f` | `@mmarukoooo` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like 50mm)'] | |
| 120 | `DS4Aq5Bkx5T` | `ref_6c01d5c0` | `@mmarukoooo` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: Inferred from look (looks like medium or standard, maybe wide due to depth)', 'focal_length_class: standard (looks like 35mm-50mm equivalent)', 'weather_atmosphere: "clear"... | |
| 121 | `DTITE0Qk3zq` | `ref_4acbd1e5` | `@mmarukoooo` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like a standard lens capturing a room)'] | |
| 122 | `DTNtLgYE-AS` | `ref_42053e7d` | `@mmarukoooo` | `clean` | `no_action` |  | |
| 123 | `DSKTuDbD2Jv` | `ref_d9f5e9b8` | `@corazon_11azul` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | materials={'material_type': 'material_type'}; materials_inline_literal_collapse | |
| 124 | `DTU-oZok5gn` | `ref_7a9fbb3b` | `@mmarukoooo` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=[']']; scene_evidence=['[']; evidence_note_key_leak=['weather_atmosphere: unknown (foliage looks green, maybe sunny outside)'] | |
| 125 | `DTnDI7Qj_VY` | `ref_a7126ab0` | `@corazon_11azul` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard (looks like 50mm)'] | |
| 126 | `DTnQ1ick-uu` | `ref_aa50abb1` | `@mmarukoooo` | `clean` | `no_action` |  | |
| 127 | `DSSO5s-Eqx5` | `ref_8c979c37` | `@corazon_11azul` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['Lower body coverage: Legs are covered by the bodysuit'] | |
| 128 | `DUnFhx2E9RS` | `ref_93be3d2b` | `@mmarukoooo` | `clean` | `no_action` |  | |
| 129 | `DU4A-zODmyX` | `ref_807a16fa` | `@aperturefnd` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" or "telephoto" (looks like a zoomed in shot of a wider scene)', 'focal_length_class: "standard" (looks like a zoomed shot)'] | |
| 130 | `DU6l-AbjtEL` | `ref_b7fd8130` | `@aperturefnd` | `clean` | `no_action` |  | |
| 131 | `DU_rCrfDoXn` | `ref_209bed97` | `@aperturefnd` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 132 | `DVKDzBvDu3l` | `ref_162afc41` | `@aperturefnd` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 133 | `DVRuG1PjiWx` | `ref_eb5b06ac` | `@aperturefnd` | `clean` | `no_action` |  | |
| 134 | `DVWl7xEDkdI` | `ref_c2080c8b` | `@aperturefnd` | `clean` | `no_action` |  | |
| 135 | `DVZAREaDgIX` | `ref_dfa757af` | `@aperturefnd` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Long-sleeved top (white), shorts/skirt (dark), gloves (black). | |
| 136 | `DVooK7oDhO4` | `ref_61aa29d7` | `@aperturefnd` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or wide (looks like a snapshot)'] | |
| 137 | `DVwIE4djgj8` | `ref_62d2036f` | `@aperturefnd` | `clean` | `no_action` |  | |
| 138 | `DV3vOjfDq2v` | `ref_70fbea5c` | `@aperturefnd` | `clean` | `no_action` |  | |
| 139 | `DV_3y1jlEh9` | `ref_d16335a1` | `@aperturefnd` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 140 | `DVyjkvAju5s` | `ref_0501708b` | `@aperturefnd` | `clean` | `no_action` |  | |
| 141 | `DULHokYjwJI` | `ref_6aeedfec` | `@corazon_11azul` | `clean` | `no_action` |  | |
| 142 | `DU0hgCjE_SN` | `ref_2379ef1a` | `@mmarukoooo` | `clean` | `no_action` |  | |
| 143 | `DS95WfOD_yx` | `ref_dc015867` | `@corazon_11azul` | `clean` | `no_action` |  | |
| 144 | `DV7f0FkE1f2` | `ref_99d31c06` | `@mmarukoooo` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 145 | `DTz3US6j1Ky` | `ref_4aaf3469` | `@corazon_11azul` | `clean` | `no_action` |  | |
| 146 | `DVir4QFEhz4` | `ref_d38fe821` | `@corazon_11azul` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['coverage: {"upper_body_coverage": "partially_covered", "lower_body_coverage": "partially_covered", "chest_visibility": "', 'focal_length_class: short-telephoto (looks like 50mm or 85mm portrai... | |
| 147 | `DQePZKejw-j` | `ref_befb678e` | `@corazon_11azul` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['**coverage:** Upper body covered, lower body covered'] | |
| 148 | `DUsk2_7lEdt` | `ref_b6cdbe4b` | `@corazon_11azul` | `clean` | `no_action` |  | |
| 149 | `DV3TgAsD0XW` | `ref_f862c289` | `@corazon_11azul` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 150 | `DV5DMhFkTeo` | `ref_28505736` | `@corazon_11azul` | `clean` | `no_action` |  | |
| 151 | `DDMYiX4yM6u` | `ref_f42f875f` | `@corazon_11azul` | `clean` | `no_action` |  | |
| 152 | `DFE2HqhyMg6` | `ref_3e3a8b42` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=16-18 or 19-22. Looks young, likely late teens or early 20s. Let's go with 19-22.; clothing_generic_garment=Bikini top (White), Bikini bottom (White).; evidence_note_key_leak=['focal_length_class: ... | |
| 153 | `DFIU2cdyxxm` | `ref_78cccd34` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: short-telephoto (looks like phone or compact, maybe 50mm equivalent)', 'focal_length_class: "standard" (looks like phone portrait mode)',... | |
| 154 | `DFKtlEWycCA` | `ref_bfcc6185` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22. Looks young. Let's say 19-22. | |
| 155 | `DFPwj2By9t2` | `ref_87fcc907` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['coverage: Upper body is partially covered (bra straps, cup)', 'focal_length_class: "short-telephoto" or "standard" (looks like phone or 50mm)'] | |
| 156 | `DFSO0jLSUuh` | `ref_54d3d7f7` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard/short-telephoto (looks like a phone or small camera)'] | |
| 157 | `DFZ2GE2Sj9l` | `ref_088dc7a8` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['lower_body_coverage: Legs are bare, wearing a skirt'] | |
| 158 | `DFct5lCS1Xa` | `ref_f7f95375` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 159 | `DFr3cyQS0W8` | `ref_c237b27a` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 160 | `DF95xPkTF0B` | `ref_f340ee70` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 161 | `DGFsiHHy61f` | `ref_14d565eb` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Black leather top, black leather skirt, silver necklace, silver earrings. | |
| 162 | `DBJDhOEh8Gp` | `ref_b1d9a7f7` | `@gooodooot` | `clean` | `no_action` |  | |
| 163 | `DFDDyIOBYOs` | `ref_efc41174` | `@gooodooot` | `token_pollution` | `reparse_raw_with_hardened_stop_lines_then_review_full_payload` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; hair={'color': '{'} | |
| 164 | `DFHkuMXBevH` | `ref_e8b0c127` | `@gooodooot` | `clean` | `no_action` |  | |
| 165 | `DFfDoWZB0jZ` | `ref_705c61e5` | `@gooodooot` | `clean` | `no_action` |  | |
| 166 | `DI1U3KeBr0y` | `ref_35e53948` | `@gooodooot` | `token_pollution` | `reparse_raw_with_hardened_stop_lines_then_review_full_payload` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; hair={'color': '{'} | |
| 167 | `DJkwwb7hWtn` | `ref_79ee39fe` | `@gooodooot` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)', 'focal_length_class: standard (looks like phone)'] | |
| 168 | `DJqTxhDBxtv` | `ref_e2c0cc7f` | `@gooodooot` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Uniform (dark jacket, white belt, cap). | |
| 169 | `DPjKENVEgE_` | `ref_f2b20846` | `@gooodooot` | `clean` | `no_action` |  | |
| 170 | `DPlTtwgkhj9` | `ref_af89f63b` | `@gooodooot` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "unknown" (hard to tell from crop)'] | |
| 171 | `DUvVAOyEsY1` | `ref_465c77f8` | `@gooodooot` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 172 | `DLNXWrwMi0x` | `ref_d88af4c4` | `@gooodooot` | `clean` | `no_action` |  | |
| 173 | `DGInM6FSU4c` | `ref_02dfe29f` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: short-telephoto (likely phone portrait mode or close up)'] | |
| 174 | `DGQgUB5ShEn` | `ref_e2fa3f3e` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard/short-telephoto (looks like a phone or small camera)'] | |
| 175 | `DGdBLW_y5Y1` | `ref_d211bcb2` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone portrait or 50mm equivalent)'] | |
| 176 | `DGf5n8Syl52` | `ref_588018da` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" or "short-telephoto" (looks like a phone selfie, maybe 50mm equivalent or slightly wider)'] | |
| 177 | `DGiKzjXSu_P` | `ref_1030670b` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard (selfie lens usually wide-ish but looks standard due to distance)'] | |
| 178 | `DGknSNDycep` | `ref_8e4d1646` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: Standard or short-telephoto (looks like a phone or small camera)'] | |
| 179 | `DGnrMPMSeTK` | `ref_42db8950` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone camera or 50mm equivalent)', 'focal_length_class: "standard" (looks like a phone portrait, maybe slightly wide angle but standard)'] | |
| 180 | `DGxkXk6Semu` | `ref_181b570e` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like phone portrait mode)'] | |
| 181 | `DG0lAVbyGdm` | `ref_3b8b971a` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 182 | `DHAoaOrynEE` | `ref_0235b1c6` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 183 | `DHGhq5dykBV` | `ref_6a3add34` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)'] | |
| 184 | `DHIxOBMy29l` | `ref_f8ca0243` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22. Looks young adult/late teen. Let's say 19-22. | |
| 185 | `DHKxa8sSvWZ` | `ref_d7610a24` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['Upper body coverage: The torso is partially covered by the top', 'Lower body coverage: The bikini bottom covers the lower body area but it\'s a thong style, so "bare" might be more accura'] | |
| 186 | `DHOYagHyw24` | `ref_a1efd4f1` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera, maybe 50mm equiv or slightly wider)'] | |
| 187 | `DNUxCCLxdis` | `ref_b269cde2` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22 (looks young adult/teen). Let's say 19-22.; evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)', 'focal_length_class: ... | |
| 188 | `DRcIh7pkaNz` | `ref_2d4dd3c2` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard (looks like 50mm or 35mm)', 'weather_atmosphere: "clear" (sky not visible but looks dry)'] | |
| 189 | `DRmS-JMkZBR` | `ref_80a9296d` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: short-telephoto or standard (looks like phone or small lens, close up)'] | |
| 190 | `DRtwSubEUnr` | `ref_fa14f290` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard/short-telephoto (looks like a portrait shot, maybe 50mm equivalent or slightly cropped)'] | |
| 191 | `DVVflMBDrRK` | `ref_079d511a` | `@katewang_kate` | `clean` | `no_action` |  | |
| 192 | `DUhjKpUkzcT` | `ref_b3dbc29f` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 193 | `DShtgrEDnr1` | `ref_acbfe0b6` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: medium (looks like a portrait shot)'] | |
| 194 | `DRKaF7BiRP0` | `ref_d125ea39` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like a portrait lens used for environmental portrait)'] | |
| 195 | `DRjXNpHDKEB` | `ref_4ab2d01b` | `@situhuiling_sco` | `clean` | `no_action` |  | |
| 196 | `DRm4eZ6jFEe` | `ref_5eb37d8c` | `@situhuiling_sco` | `clean` | `no_action` |  | |
| 197 | `DRsm9_UjBc5` | `ref_1a026dd8` | `@situhuiling_sco` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like a portrait shot, maybe 50mm)'] | |
| 198 | `DR19Xe8j1mV` | `ref_15fbb408` | `@situhuiling_sco` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['lower_body_coverage: partially_covered (hips/buttocks visible, bottom covered)', 'focal_length_class: standard (likely phone camera)'] | |
| 199 | `DR566WkCvYh` | `ref_52a52c80` | `@situhuiling_sco` | `clean` | `no_action` |  | |
| 200 | `DSChlzJlM_E` | `ref_0246b854` | `@situhuiling_sco` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=Hard to tell from back, but body shape suggests adult, likely 20s-30s. Let's say 23-29 or 30-39. Given the physique, 23-; clothing_generic_garment=White dress (long, sleeveless or strapless). Mater... | |
| 201 | `DSZLQYlkXQ2` | `ref_f2c95a49` | `@situhuiling_sco` | `clean` | `no_action` |  | |
| 202 | `DShvQ-XFMsp` | `ref_87512826` | `@situhuiling_sco` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like a portrait shot, maybe 50mm)'] | |
| 203 | `DU1wDOED-MX` | `ref_aaffa759` | `@situhuiling_sco` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: "standard" (looks like 50mm or 85mm portrait)'] | |
| 204 | `DQ64llJD1Lo` | `ref_3e1856b5` | `@situhuiling_sco` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 205 | `DRZ7n3vjWZM` | `ref_ff4f4c64` | `@situhuiling_sco` | `clean` | `no_action` |  | |
| 206 | `DREWg4AiXQh` | `ref_78c1a000` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "standard" (Looks like 50mm equivalent)'] | |
| 207 | `DQwO2DxiS-R` | `ref_9c690113` | `@katewang_kate` | `clean` | `no_action` |  | |
| 208 | `DQt0nt5iYIU` | `ref_87946077` | `@katewang_kate` | `clean` | `no_action` |  | |
| 209 | `DQrFL1xE6T9` | `ref_d0ddacc3` | `@katewang_kate` | `clean` | `no_action` |  | |
| 210 | `DQqRNWBiS_C` | `ref_82843253` | `@katewang_kate` | `clean` | `no_action` |  | |
| 211 | `DQoKtBrCbCg` | `ref_8529ef72` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 212 | `DQmJ-r9CXlb` | `ref_f7a1855c` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: short-telephoto / standard (likely phone camera)'] | |
| 213 | `DQiZTV6iV9g` | `ref_fcf8fbdc` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 214 | `DQeLiNviVLI` | `ref_ef30eed9` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like 50mm)'] | |
| 215 | `DQZR3jTiUbe` | `ref_08cc2f8b` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like a compact point-and-shoot, maybe 35mm equiv)'] | |
| 216 | `DQWq4p3iZQt` | `ref_c98147bf` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['coverage: {"upper_body_coverage": "covered", "lower_body_coverage": "partially_covered", "chest_visibility": "covered", ', '* focal_length_class: "short-telephoto" (looks like 50mm-85mm equiva... | |
| 217 | `DQT52MpidMv` | `ref_f1488800` | `@katewang_kate` | `clean` | `no_action` |  | |
| 218 | `DQRaP_MiTvY` | `ref_11ba9dd6` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; coverage_notes_key_leak=upper_body_coverage: covered. lower_body_coverage: not_visible. chest_visibility: covered. chest_coverage_method: garment.; pose_gesture_key_leak=stance: stan... | |
| 219 | `DQMgCrxCT0T` | `ref_8d2749ce` | `@katewang_kate` | `clean` | `no_action` |  | |
| 220 | `DQHJcfqCR3n` | `ref_fc1ccc2e` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like a phone or 50mm)'] | |
| 221 | `DP77SHAiXlm` | `ref_33919dae` | `@katewang_kate` | `clean` | `no_action` |  | |
| 222 | `DP5-xlyiSpw` | `ref_140ac9df` | `@katewang_kate` | `clean` | `no_action` |  | |
| 223 | `DP2ypdjCQ_Z` | `ref_1ed98bdb` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 224 | `DPvzblLCQHC` | `ref_8ca0edbb` | `@katewang_kate` | `clean` | `no_action` |  | |
| 225 | `DPswL-mCdst` | `ref_7fd68796` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 226 | `DPk2sCxiYQF` | `ref_38c3eafc` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 227 | `DPYSP9viR6R` | `ref_b74ea933` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: short-telephoto (selfie lens likely)'] | |
| 228 | `DPQ7vQTCYWK` | `ref_6939ed4e` | `@katewang_kate` | `clean` | `no_action` |  | |
| 229 | `DPL5frACfYX` | `ref_7e4cafc8` | `@katewang_kate` | `clean` | `no_action` |  | |
| 230 | `DPGJimwiSlO` | `ref_ca4c1bec` | `@katewang_kate` | `clean` | `no_action` |  | |
| 231 | `DPDvSGpCaRW` | `ref_ddbd45a0` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: short-telephoto (looks like a portrait lens)'] | |
| 232 | `DO8Bq1ciUCF` | `ref_4d3073b0` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like a portrait lens)'] | |
| 233 | `DO49ZKwCWhT` | `ref_de63617c` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera or standard lens)'] | |
| 234 | `DOzulrYCfp8` | `ref_444c3167` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 235 | `DOviJlDCWo_` | `ref_a18707d2` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard/short-telephoto (looks like phone camera)'] | |
| 236 | `DOsmIWDiaOa` | `ref_32f9ee45` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; clothing_generic_garment=garment_type: top, color: dark brown, material: fabric, fit: slim, style_era: modern; coverage_notes_key_leak=upper_body_coverage: partially_covered, lower_b... | |
| 237 | `DOpkXP8iTpD` | `ref_e172476f` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "standard" (Looks like a phone portrait or 50mm equivalent)'] | |
| 238 | `DOkUlQMife1` | `ref_dc959f03` | `@katewang_kate` | `clean` | `no_action` |  | |
| 239 | `DUlWkH_EsuT` | `ref_3952145d` | `@bayareashitpeople_` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "short-telephoto" (looks like a phone camera, maybe 50mm equiv)'] | |
| 240 | `DUz3KXvEn8g` | `ref_d053b78b` | `@bayareashitpeople_` | `clean` | `no_action` |  | |
| 241 | `DVVy9iOkpD_` | `ref_80eb97fa` | `@bayareashitpeople_` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 242 | `DVlqJyCErZc` | `ref_4172b3b1` | `@bayareashitpeople_` | `clean` | `no_action` |  | |
| 243 | `C0JMGZTrTXw` | `ref_1b634ada` | `@bayareashitpeople_` | `clean` | `no_action` |  | |
| 244 | `C3xU6eTpMyF` | `ref_393a775b` | `@ning_8927` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22. Looks young adult/late teen. Let's go with 19-22 based on skin texture and maturity.; evidence_note_key_leak=['focal_length_class: standard or sho... | |
| 245 | `C7O37UWJoey` | `ref_881743f7` | `@ning_8927` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=19-22 or 23-29. Looks young adult. Let's say 19-22.; evidence_note_key_leak=['focal_length_class: standard (looks like 50mm)', 'focal_length_class: "standard" (Looks like 50mm or 85mm portrait)'] | |
| 246 | `C7T8vHVJ6Bt` | `ref_0c86a57d` | `@ning_8927` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; environment_set_d... | |
| 247 | `DPlyDpsE24p` | `ref_d7159733` | `@ishinoko.jp` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or standard lens)'] | |
| 248 | `DPl3hHdk1Dt` | `ref_7e2ce0f9` | `@ishinoko.jp` | `clean` | `no_action` |  | |
| 249 | `DPl3tUrExlp` | `ref_6fa1aca7` | `@ishinoko.jp` | `clean` | `no_action` |  | |
| 250 | `DP_OVoigHzK` | `ref_12e91d25` | `@ishinoko.jp` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; clothing_generic_garment=Light blue button-down shirt, black apron, baseball cap (blue with yellow text). | |
| 251 | `DQBtighAHKA` | `ref_3691380c` | `@ishinoko.jp` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Yellow t-shirt, dark pants/shorts (partially visible). | |
| 252 | `DQHdpfvk4fi` | `ref_6efb6796` | `@ishinoko.jp` | `token_pollution` | `reparse_raw_with_hardened_stop_lines_then_review_full_payload` | object_labels=[']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; environment_set_dressing=['[']; training_lane_hints=['[']; t... | |
| 253 | `DQIr_CCEgW8` | `ref_f1bdf7d7` | `@ishinoko.jp` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=16-18 or 19-22 (looks young adult).; clothing_generic_garment=Green sleeveless top, patterned pants.; evidence_note_key_leak=['focal_length_class: standard (looks like a phone camera, maybe 24mm eq... | |
| 254 | `DQIso5ckh99` | `ref_62c11e5c` | `@ishinoko.jp` | `clean` | `no_action` |  | |
| 255 | `DQIlwaGEvQG` | `ref_6892e90f` | `@ishinoko.jp` | `clean` | `no_action` |  | |
| 256 | `DQQJI6DknuH` | `ref_c8109c64` | `@ishinoko.jp` | `clean` | `no_action` |  | |
| 257 | `DQdv2QKk-Zk` | `ref_52dc327c` | `@ishinoko.jp` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or medium (looks like a phone or small camera)'] | |
| 258 | `DOge1B7kWVn` | `ref_3cfe692e` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like 50mm equivalent)'] | |
| 259 | `DOU8MWZic6l` | `ref_2174cbef` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 260 | `DOOXOYOCVRa` | `ref_1c3c18f1` | `@katewang_kate` | `clean` | `no_action` |  | |
| 261 | `DOLVLS6CZ7D` | `ref_d3f4af70` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 262 | `DOIrkqPiXNr` | `ref_334205df` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like a phone or 50mm equivalent)'] | |
| 263 | `DOFgh8PiaWd` | `ref_1983e183` | `@katewang_kate` | `clean` | `no_action` |  | |
| 264 | `DN96gZcCelc` | `ref_a064059d` | `@katewang_kate` | `clean` | `no_action` |  | |
| 265 | `DN7rYcYCRp-` | `ref_c4887547` | `@katewang_kate` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | materials={'material_type': 'material_type'}; materials_inline_literal_collapse | |
| 266 | `DN52vWKibrd` | `ref_194213db` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['`environment`: location_type: studio (looks like a white seamless or textured wall, lighting is very controlled), locati'] | |
| 267 | `DN0IwcP0vzv` | `ref_abe2b450` | `@katewang_kate` | `clean` | `no_action` |  | |
| 268 | `DNvXo4q0poF` | `ref_729505fd` | `@katewang_kate` | `clean` | `no_action` |  | |
| 269 | `DNsCmhxUuek` | `ref_1a4d5b8a` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 270 | `DNnlQOMJTij` | `ref_6ccf3ea7` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 271 | `DNk69wxpsnk` | `ref_25c0ab72` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like 50mm or 85mm portrait)'] | |
| 272 | `DNYPpDYJ_Qd` | `ref_305a4fdb` | `@katewang_kate` | `clean` | `no_action` |  | |
| 273 | `DNVEiIuJl5O` | `ref_e3c13079` | `@katewang_kate` | `clean` | `no_action` |  | |
| 274 | `DNQTjC_JexC` | `ref_6d19ebbc` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or small camera)'] | |
| 275 | `DNDtRy8pGLd` | `ref_06c838f5` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 276 | `DM-mBX6y9FK` | `ref_7ad0f984` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard (looks like a portrait lens, maybe 50mm or 85mm equivalent)'] | |
| 277 | `DM63okDp-ND` | `ref_bea588f8` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; coverage_notes_key_leak=upper_body_coverage: covered, lower_body_coverage: covered (skirt covers hips/thighs), chest_visibility: partially_visible (collar visible),; evidence_note_ke... | |
| 278 | `DM4tB1jJfic` | `ref_09559520` | `@katewang_kate` | `clean` | `no_action` |  | |
| 279 | `DM27WCvpANv` | `ref_7770bacd` | `@katewang_kate` | `clean` | `no_action` |  | |
| 280 | `DReaF2Fk745` | `ref_23a60dc9` | `@ellie_bound` | `clean` | `no_action` |  | |
| 281 | `DRfD1l_CbGX` | `ref_dd1aecdb` | `@ellie_bound` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 282 | `DRpVWqUicFZ` | `ref_9e0f8528` | `@ellie_bound` | `clean` | `no_action` |  | |
| 283 | `DR9IKldiaGJ` | `ref_52499be3` | `@ellie_bound` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like a phone camera, maybe 24-35mm equivalent)'] | |
| 284 | `DSC28JPCWJK` | `ref_74b5de88` | `@ellie_bound` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 285 | `DSRfFEEiRhu` | `ref_1d222116` | `@ellie_bound` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['coverage: Upper body covered (top), lower body partially covered (legs exposed but bound)', 'weather_atmosphere: clear (outside looks bright)'] | |
| 286 | `DTU2OKCid9r` | `ref_eb9bc262` | `@ellie_bound` | `clean` | `no_action` |  | |
| 287 | `DTaYIskCdAC` | `ref_e6d722bb` | `@ellie_bound` | `clean` | `no_action` |  | |
| 288 | `DTjlyIiCRZy` | `ref_9cec755e` | `@ellie_bound` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Black latex bodysuit, gloves. | |
| 289 | `DTrb6MKCav_` | `ref_e956e4ee` | `@ellie_bound` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=[']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; environment_set_dressing=['[']; hair={'color': '{'}; evidenc... | |
| 290 | `DT0ZmFAicas` | `ref_44b8314f` | `@ellie_bound` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=White blouse, black skirt (short), black stockings. | |
| 291 | `DUFSMuaiZSo` | `ref_ee118ab4` | `@ellie_bound` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=White shirt (unbuttoned), black pants, blue belt. | |
| 292 | `DMuf9utpK3Q` | `ref_54b5be97` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['coverage: upper covered, lower partially covered (waist visible), chest covered'] | |
| 293 | `DMsf1TVJGlW` | `ref_27557fde` | `@katewang_kate` | `clean` | `no_action` |  | |
| 294 | `CbF6TOrJZeL` | `ref_a6a55561` | `@randi852__` | `clean` | `no_action` |  | |
| 295 | `CbG1fk7l_ES` | `ref_549c0702` | `@randi852__` | `clean` | `no_action` |  | |
| 296 | `Cc7ud6JASTI` | `ref_2fbc6f7b` | `@randi852__` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "unknown" (looks like phone camera, maybe short telephoto or standard)', 'focal_length_class: "unknown" (phone camera likely)'] | |
| 297 | `DMo0YydpbBW` | `ref_1d5f0acc` | `@katewang_kate` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; training_lane_hin... | |
| 298 | `DMh7WvAJvAW` | `ref_d0df451e` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 299 | `DMfrj6tpMvw` | `ref_273fd649` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* *coverage:* Upper body: Covered (strapless but dress covers chest)', '* *focal_length_class:* Standard (looks like a portrait shot)'] | |
| 300 | `Cz08NBgPIju` | `ref_9188d0d6` | `@catssyrup` | `clean` | `no_action` |  | |
| 301 | `C0BEBwTPRTI` | `ref_26e37c9e` | `@catssyrup` | `clean` | `no_action` |  | |
| 302 | `DMdGmHgJW4r` | `ref_25e2ab21` | `@katewang_kate` | `clean` | `no_action` |  | |
| 303 | `DMXRRtPJnzg` | `ref_e5b1fac5` | `@katewang_kate` | `clean` | `no_action` |  | |
| 304 | `DMSBiv-J-U6` | `ref_3ae9c367` | `@katewang_kate` | `clean` | `no_action` |  | |
| 305 | `DMCe5WUJJ38` | `ref_b02e17cb` | `@katewang_kate` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; hair={'color': '{... | |
| 306 | `DMABTdKJqn8` | `ref_57168957` | `@katewang_kate` | `clean` | `no_action` |  | |
| 307 | `DL99UL1ppkw` | `ref_82d55a76` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 308 | `DLQ308rhVx7` | `ref_9af5baed` | `@university.tw` | `clean` | `no_action` |  | |
| 309 | `DL8-p56p6AX` | `ref_ebba239f` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 310 | `DLmomxsJkk4` | `ref_f8025e12` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "standard" (looks like a phone or standard lens)'] | |
| 311 | `DLhbJvWpyd_` | `ref_67e38d6a` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "standard" (looks like a portrait shot, not extreme wide or telephoto)'] | |
| 312 | `CtMeb5wSZNh` | `ref_b9c48aa1` | `@lhkpr_4786` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 313 | `DLgqmBZpHWF` | `ref_1e92fa9a` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "standard" (looks like a phone camera, maybe 50mm equivalent)'] | |
| 314 | `DLe4MdYJznl` | `ref_6881533f` | `@katewang_kate` | `clean` | `no_action` |  | |
| 315 | `DLbsGjapw2A` | `ref_bebb5d34` | `@katewang_kate` | `clean` | `no_action` |  | |
| 316 | `DLUpzFyJaBi` | `ref_d75509c9` | `@katewang_kate` | `clean` | `no_action` |  | |
| 317 | `DLSCJ6qpW0I` | `ref_94ce604a` | `@katewang_kate` | `clean` | `no_action` |  | |
| 318 | `DLKUtqopNZ_` | `ref_d0fe20df` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Kimono (blue with floral pattern), Obi (red sash), Geta (sandals). | |
| 319 | `DLE78-DJTcn` | `ref_bdf2714f` | `@katewang_kate` | `token_pollution` | `reparse_raw_with_hardened_stop_lines_then_review_full_payload` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; environment_set_d... | |
| 320 | `DLCVjOspLUa` | `ref_91d567fa` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a portrait lens)'] | |
| 321 | `DK9hALvJp9E` | `ref_ab6efece` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['**coverage:** Upper body is covered by the shirt, but the top button is open'] | |
| 322 | `DK6RC0HpeK_` | `ref_a8b5ed45` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 323 | `DKyTBp2uYXU` | `ref_9fc085dd` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like 50mm or 35mm equivalent)', '* weather_atmosphere: overcast / clear (sky not visible, light is soft)'] | |
| 324 | `DKrwIzlJofB` | `ref_355910f9` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like phone or 50mm equiv)'] | |
| 325 | `DKodexTpj7M` | `ref_d2d03ed2` | `@katewang_kate` | `clean` | `no_action` |  | |
| 326 | `DKmfUQmpXO2` | `ref_e02011e0` | `@katewang_kate` | `clean` | `no_action` |  | |
| 327 | `DKjzcAPJss7` | `ref_596456e4` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a portrait shot but with background)'] | |
| 328 | `DKhSKRCphaV` | `ref_77c6df28` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 329 | `DKemxydpbLC` | `ref_c5d8355c` | `@katewang_kate` | `clean` | `no_action` |  | |
| 330 | `DKcHBw4JHq9` | `ref_b066b7c3` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or compact camera)'] | |
| 331 | `DKPP9JApceP` | `ref_ccfe1ebe` | `@katewang_kate` | `clean` | `no_action` |  | |
| 332 | `DKKO7oRJdXR` | `ref_64ba2d15` | `@katewang_kate` | `clean` | `no_action` |  | |
| 333 | `CuQK0TsMVRC` | `ref_07973837` | `@shengpppppan` | `clean` | `no_action` |  | |
| 334 | `CvFObgPsY5C` | `ref_75f1bfa9` | `@shengpppppan` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" or "wide" (looks like a view from a balcony, maybe standard or slightly wide)'] | |
| 335 | `CvSK9p7Mkd5` | `ref_f3f9ab90` | `@shengpppppan` | `clean` | `no_action` |  | |
| 336 | `Cv4fMqdMwPz` | `ref_761ca5fc` | `@shengpppppan` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 337 | `Cv4gbz5MBV7` | `ref_909a9ee6` | `@shengpppppan` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard or wide (looks like a standard lens capturing a room)'] | |
| 338 | `CxTiQFZrZou` | `ref_d533e0cc` | `@shengpppppan` | `clean` | `no_action` |  | |
| 339 | `CzMHdtGMs7Y` | `ref_a7be69e2` | `@shengpppppan` | `clean` | `no_action` |  | |
| 340 | `C1fFRlys89a` | `ref_044df974` | `@shengpppppan` | `clean` | `no_action` |  | |
| 341 | `C74Lu9lNnaK` | `ref_ce6f1910` | `@shengpppppan` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: "standard" (looks like a phone camera or 35mm equivalent)'] | |
| 342 | `DKpyKoPs0Ee` | `ref_c232e4a4` | `@shengpppppan` | `clean` | `no_action` |  | |
| 343 | `DRIpBIVDNR3` | `ref_fce56e34` | `@shengpppppan` | `clean` | `no_action` |  | |
| 344 | `DKEWmIVp5hx` | `ref_2acd1f2e` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 345 | `DJvovLVpBo-` | `ref_10bf3362` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 346 | `DLHf5WjyuX9` | `ref_03028e3f` | `@h__lei` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone or 50mm equivalent)'] | |
| 347 | `DM54bP-TWvA` | `ref_23ac0070` | `@h__lei` | `clean` | `no_action` |  | |
| 348 | `DND0OGOSaXJ` | `ref_23157aff` | `@h__lei` | `clean` | `no_action` |  | |
| 349 | `DOs7_g5jx6L` | `ref_18402c3f` | `@h__lei` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (Looks like a phone camera or standard lens)'] | |
| 350 | `DPGyhtqj_Fm` | `ref_c11f5e8b` | `@h__lei` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: "standard" (looks like a portrait shot, maybe 50mm equivalent)', 'focal_length_class: "standard" (looks like a portrait lens)'] | |
| 351 | `DPbb0wXEXyu` | `ref_6a0991c4` | `@h__lei` | `clean` | `no_action` |  | |
| 352 | `DRKVpDTD8jy` | `ref_46bc9158` | `@h__lei` | `clean` | `no_action` |  | |
| 353 | `DUTrutME2ug` | `ref_6a22083a` | `@h__lei` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['coverage: upper covered, lower covered, chest covered, chest coverage garment', 'focal_length_class: standard (looks like phone camera, slightly cropped)'] | |
| 354 | `DGape2ruL_-` | `ref_5e83bfa7` | `@jamiewangcomedy` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like a portrait shot)'] | |
| 355 | `DHTLEVTKPu6` | `ref_150d3e76` | `@jamiewangcomedy` | `clean` | `no_action` |  | |
| 356 | `DHf2GEEqpUA` | `ref_978dc305` | `@jamiewangcomedy` | `clean` | `no_action` |  | |
| 357 | `DIYvO7CT1WT` | `ref_c25b8d7b` | `@jamiewangcomedy` | `clean` | `no_action` |  | |
| 358 | `DObbGDgDEpz` | `ref_ba29fa2f` | `@jamiewangcomedy` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Patterned dress (red/purple/white zigzag), white shoes. | |
| 359 | `DOe8KVyCGHD` | `ref_f9497a72` | `@jamiewangcomedy` | `clean` | `no_action` |  | |
| 360 | `DUnp_paEUlo` | `ref_7075e4ce` | `@h__lei` | `clean` | `no_action` |  | |
| 361 | `DUyKU-pDw7q` | `ref_fc859f8a` | `@h__lei` | `clean` | `no_action` |  | |
| 362 | `DU96IHPkY0K` | `ref_25ca59cf` | `@h__lei` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera, maybe 50mm equiv or slightly wider)', 'focal_length_class: standard (looks like phone portrait mode or standard lens)', 'weather_atmosphe... | |
| 363 | `DV_mcnXD6F3` | `ref_651d1f6f` | `@h__lei` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 364 | `DJmFT06pdXW` | `ref_e3b18fc1` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 365 | `DJihDo0J3Xs` | `ref_20fac3d7` | `@katewang_kate` | `clean` | `no_action` |  | |
| 366 | `DGCXFk2zde2` | `ref_36f880e1` | `@doing4732` | `clean` | `no_action` |  | |
| 367 | `DGDpcMnT2q8` | `ref_0043546b` | `@doing4732` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or short-telephoto (looks like a portrait crop)'] | |
| 368 | `DGbD3nVzmDi` | `ref_a8b1aa67` | `@doing4732` | `clean` | `no_action` |  | |
| 369 | `DGuK8rxz5Wk` | `ref_69c35072` | `@doing4732` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=19-22" or "23-29". Feet look young/developed. Let's say "23-29.; evidence_note_key_leak=['coverage: {"upper_body_coverage": "not_visible", "lower_body_coverage": ... | |
| 370 | `DHAtCVrTVlj` | `ref_aa5b0255` | `@doing4732` | `clean` | `no_action` |  | |
| 371 | `DKZgmGrzuZe` | `ref_033cf239` | `@doing4732` | `clean` | `no_action` |  | |
| 372 | `DLhFtiXTTJu` | `ref_56eaf7dd` | `@doing4732` | `clean` | `no_action` |  | |
| 373 | `DMKVsiHzMe3` | `ref_db9a4ab1` | `@doing4732` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 374 | `DMUpnjtzrCy` | `ref_9c671935` | `@doing4732` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=16-18 or 19-22 (looks young adult/teen anime style). Let's go with 16-18 based on typical anime character design, but "n; clothing_generic_garment=None visible on... | |
| 375 | `DMfXd-RRVcc` | `ref_25867eaf` | `@doing4732` | `clean` | `no_action` |  | |
| 376 | `DPfj89ckTKZ` | `ref_6f70b71a` | `@doing4732` | `clean` | `no_action` |  | |
| 377 | `DRZ3SG8EvTq` | `ref_ef20f575` | `@doing4732` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "unknown" (hard to tell from crop)'] | |
| 378 | `DJdoIxUJbx6` | `ref_25639f03` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 379 | `DJbliI6pH-7` | `ref_d3d91436` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Black top (short sleeves), White skirt (visible lower part). | |
| 380 | `DJZMmsjJDNV` | `ref_4b13bc8b` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like 50mm or 85mm portrait)'] | |
| 381 | `DJRfB0XprWB` | `ref_6e5baf07` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; estimated_age_range=19-22 or 23-29. Looks young adult. Let's go with 19-22 based on skin texture and features. | |
| 382 | `DI8jRAFJbe_` | `ref_4833fb21` | `@katewang_kate` | `clean` | `no_action` |  | |
| 383 | `DI0p6gcpEAd` | `ref_d4c68b25` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 384 | `DIxsUEgp83B` | `ref_6e1250f7` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 385 | `DIvhFixpbo8` | `ref_6475402b` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 386 | `DIgGey5phol` | `ref_753052c2` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard (looks like 50mm or 85mm portrait)'] | |
| 387 | `DIaqWLPJqPp` | `ref_6c48b853` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like a portrait lens)'] | |
| 388 | `DITLxfPJe6N` | `ref_757cbb92` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or small camera)'] | |
| 389 | `DIOZOKNplpm` | `ref_996f8703` | `@katewang_kate` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 390 | `DIL7ydppJ6i` | `ref_74906cbb` | `@katewang_kate` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; training_lane_hin... | |
| 391 | `DVTJjiDkqxb` | `ref_6ed00cfc` | `@agatayamaguchi_colle` | `clean` | `no_action` |  | |
| 392 | `DVQgD7HkjxH` | `ref_8e22ae8a` | `@agatayamaguchi_colle` | `clean` | `no_action` |  | |
| 393 | `CZbRKcFL1jQ` | `ref_206a17b2` | `@university.tw` | `token_pollution` | `reparse_raw_with_hardened_stop_lines_then_review_full_payload` | object_labels=[']'] | |
| 394 | `DHYbpYSv7Tx` | `ref_156b901c` | `@attractive_hotness_girls` | `clean` | `no_action` |  | |
| 395 | `CUuNy2WFVnR` | `ref_2d8ed6ae` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* *coverage:* {"upper_body_coverage": "partially_covered", "lower_body_coverage": "covered", "chest_visibility": "partia', 'coverage: {"upper_body_coverage":... | |
| 396 | `DTmdhw7EuDm` | `ref_8ca81b44` | `@university.tw` | `clean` | `no_action` |  | |
| 397 | `DHdr_IlyUck` | `ref_fcf52caf` | `@attractive_hotness_girls` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "standard" (Looks like phone camera, maybe 50mm equiv or slightly wider)', '* focal_length_class: standard (looks like phone portrait mode)'] | |
| 398 | `DU8BSsnkn3b` | `ref_60dd29a4` | `@agatayamaguchi_colle` | `clean` | `no_action` |  | |
| 399 | `CXTAl0il8aj` | `ref_85e7d9c9` | `@university.tw` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like phone camera, maybe 50mm equiv)'] | |
| 400 | `C7EgwDAyGXD` | `ref_345bcf3c` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard/short-telephoto (looks like phone or small camera)'] | |
| 401 | `CZlXfEppdkP` | `ref_de074948` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "unknown" (High angle, likely phone or wide)'] | |
| 402 | `C2ZczOGrjOQ` | `ref_0a385cc3` | `@zacgel` | `clean` | `no_action` |  | |
| 403 | `DUk6IV4j3bD` | `ref_de119a5e` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Grey coat (wool?), Black cap. | |
| 404 | `DUI03Uuj61y` | `ref_9d011e39` | `@zacgel` | `clean` | `no_action` |  | |
| 405 | `DRzia4dD8tV` | `ref_7e0ac291` | `@zacgel` | `clean` | `no_action` |  | |
| 406 | `DRZKNCFjyM_` | `ref_0e279cb5` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like phone lens)'] | |
| 407 | `DQ1JP1qjwzT` | `ref_113ac1ae` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like 50mm or 85mm portrait)', 'focal_length_class: standard (looks like 50mm or 85mm portrait lens)'] | |
| 408 | `DKrXOGQTrpD` | `ref_12f5be34` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard (looks like phone camera or 50mm equivalent)'] | |
| 409 | `DNCulBFTEAk` | `ref_ca9fe6e8` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['Upper body coverage: Covered (t-shirt)'] | |
| 410 | `DQtlvxoD_IT` | `ref_a46ab5a9` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* **coverage:** Upper body covered (sweater), lower body covered (jeans)', '* weather_atmosphere: clear / overcast (sky not visible, but looks dry)'] | |
| 411 | `DQdp9iTj0FY` | `ref_3f1e121d` | `@zacgel` | `clean` | `no_action` |  | |
| 412 | `DQoPtIMj_I3` | `ref_ecab27b2` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: "standard" (Likely 50mm or similar for portrait)'] | |
| 413 | `DKHBVQsubPs` | `ref_e5160c3e` | `@zacgel` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=['{', 'label', 'confidence', 'region', '}', ']']; scene_evidence=['[']; insights_hashtags=['[']; environment_foreground=['[']; environment_midground=['[']; environment_background=['[']; environment_set_d... | |
| 414 | `DJyiAiQTrjm` | `ref_c1105928` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 415 | `DKTySBfu4u6` | `ref_eb88c391` | `@zacgel` | `clean` | `no_action` |  | |
| 416 | `DNz47pl3i2G` | `ref_5e647518` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 417 | `DPTlybUD3lk` | `ref_523f3126` | `@zacgel` | `clean` | `no_action` |  | |
| 418 | `CwcRKY-uMRe` | `ref_fb1af135` | `@maorennnn` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 419 | `CwfFCgmrqoa` | `ref_eb49cded` | `@maorennnn` | `clean` | `no_action` |  | |
| 420 | `CwnX5PnLMvr` | `ref_8783a4cf` | `@maorennnn` | `clean` | `no_action` |  | |
| 421 | `CwpvmLZLk1s` | `ref_95a4f701` | `@maorennnn` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 422 | `CwsB4JzLOSG` | `ref_08598e62` | `@maorennnn` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['**coverage:** upper_body_coverage: partially_covered (shoulder/chest area visible but mostly hidden), lower_body_coverag'] | |
| 423 | `Cxa8tvFxQ-x` | `ref_f02bd1e4` | `@maorennnn` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard or wide (looks like a phone or standard lens)'] | |
| 424 | `Cy02XJRr8iW` | `ref_a8ccff5d` | `@maorennnn` | `clean` | `no_action` |  | |
| 425 | `CzgB2VZuc0c` | `ref_d3e4ddbd` | `@maorennnn` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; clothing_generic_garment=[] (Legs are bare, no clothing on legs) | |
| 426 | `Cz_WBdhr3X2` | `ref_905ba535` | `@maorennnn` | `clean` | `no_action` |  | |
| 427 | `C0buzKbr_Jg` | `ref_07000695` | `@maorennnn` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 428 | `C0i0I25uLtl` | `ref_b96f2959` | `@maorennnn` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=16-18 or 19-22 (young adult).; clothing_generic_garment=None visible (topless).; evidence_note_key_leak=['* *coverage:* Upper body: Bare'] | |
| 429 | `C5nkoElLzW9` | `ref_d5b15091` | `@maorennnn` | `clean` | `no_action` |  | |
| 430 | `DHOKz6GzG7M` | `ref_fcc0695d` | `@zacgel` | `clean` | `no_action` |  | |
| 431 | `DG-sD_KTnoL` | `ref_84cb7980` | `@zacgel` | `clean` | `no_action` |  | |
| 432 | `DKOsEoZOacz` | `ref_4620c465` | `@zacgel` | `clean` | `no_action` |  | |
| 433 | `DGxOQUvu58X` | `ref_1dbea223` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 434 | `DODQgIfkdjA` | `ref_83654ea9` | `@zacgel` | `clean` | `no_action` |  | |
| 435 | `DF7hKrrTSf1` | `ref_c28308de` | `@zacgel` | `clean` | `no_action` |  | |
| 436 | `DEPfjuzzNA5` | `ref_a9d2c660` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; clothing_generic_garment=White long sleeve top (looks like linen or cotton), light blue jeans (visible at bottom).; evidence_note_key_leak=['* focal_length_class: standard / short-te... | |
| 437 | `CtS225VyXYA` | `ref_5cac5208` | `@lhkpr_4786` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: "standard" (looks like phone camera)'] | |
| 438 | `CtonN9QNqFJ` | `ref_467cda3c` | `@lhkpr_4786` | `clean` | `no_action` |  | |
| 439 | `Cu_5cp2tj0h` | `ref_6c4ffc69` | `@lhkpr_4786` | `clean` | `no_action` |  | |
| 440 | `CvXJ8SvNLFc` | `ref_1f1f6334` | `@lhkpr_4786` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=Face is barely visible (chin). Hard to tell. "unknown" or "not_visible". Let's say "not_visible" because the face is mos; evidence_note_key_leak=['focal_length_class: "unknown" (hard to tell exact,... | |
| 441 | `CxOmjYftWGp` | `ref_5a85183c` | `@lhkpr_4786` | `clean` | `no_action` |  | |
| 442 | `CxtCmqeNW6k` | `ref_ed0ddbd5` | `@lhkpr_4786` | `clean` | `no_action` |  | |
| 443 | `DLdDmdcN4Gv` | `ref_99e53898` | `@lhkpr_4786` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; pose_gesture_key_leak=stance: not_visible, etc. | |
| 444 | `DTF0vuWFCYP` | `ref_0ecc2129` | `@lhkpr_4786` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone camera, maybe 24mm equivalent)'] | |
| 445 | `CnPKWDIqTVa` | `ref_108aa4cd` | `@lhkpr_4786` | `clean` | `no_action` |  | |
| 446 | `Cr0uCVZN7gT` | `ref_eb2d4c6a` | `@lhkpr_4786` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 447 | `DIHAWB8ziS2` | `ref_ca0dd193` | `@claiiireshy` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard/short-telephoto (looks like 50mm-85mm equivalent)'] | |
| 448 | `DDyTIF9TEwa` | `ref_d9ab639e` | `@zacgel` | `clean` | `no_action` |  | |
| 449 | `DBlrCrBTORQ` | `ref_d5cf1ba3` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 450 | `CqpVjkCggbr` | `ref_886b1e53` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=One-piece swimsuit (black). | |
| 451 | `CpzvuOGJG4n` | `ref_52d3d00a` | `@zacgel` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or 50mm equivalent)', 'focal_length_class: standard (looks like phone portrait mode or 50mm)', 'focal_length_class: standard (looks like phone ... | |
| 452 | `DER21ZnORwD` | `ref_cafc18d7` | `@deany1n` | `clean` | `no_action` |  | |
| 453 | `DK1ijX7oi3P` | `ref_345ba5ed` | `@deany1n` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | estimated_age_range=23-29 or 30-39. They look like young adults. | |
| 454 | `DUGTIQIEU7z` | `ref_fb551bd7` | `@deany1n` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Black t-shirt, necklace. | |
| 455 | `C0k-gmyPryz` | `ref_e4339cc5` | `@clio1008` | `clean` | `no_action` |  | |
| 456 | `C4dD6vYPRAd` | `ref_dd2e75c4` | `@clio1008` | `clean` | `no_action` |  | |
| 457 | `C5Aelqsvv0a` | `ref_b0227b08` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: "short-telephoto" (likely macro)'] | |
| 458 | `DULFnqHCEBW` | `ref_e37ee706` | `@a.sound._` | `clean` | `no_action` |  | |
| 459 | `DUOsMmHCM_L` | `ref_57f860a8` | `@a.sound._` | `clean` | `no_action` |  | |
| 460 | `DUcF3EfCLHY` | `ref_72d03fa2` | `@a.sound._` | `clean` | `no_action` |  | |
| 461 | `CjVzV84N7gZ` | `ref_d3f0ea65` | `@sonirotaru` | `clean` | `no_action` |  | |
| 462 | `CszBWGyNBtV` | `ref_ab530cd1` | `@sonirotaru` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or small camera)', 'weather_atmosphere: unknown (trees look green, likely clear)'] | |
| 463 | `Cu66_mztJ-p` | `ref_74bb0c27` | `@sonirotaru` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: "standard" (looks like a portrait lens)'] | |
| 464 | `CvJ2dXStXR3` | `ref_feee94ff` | `@sonirotaru` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | training_style_tags=['texture']; materials_inline_literal_collapse | |
| 465 | `Cvg8J4nt7NF` | `ref_ef23d7b9` | `@sonirotaru` | `clean` | `no_action` |  | |
| 466 | `CwF6tYXtg1D` | `ref_a473161a` | `@sonirotaru` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | clothing_generic_garment=Bikini (two-piece swimsuit). | |
| 467 | `Cyu7z8YxqTT` | `ref_5c8094df` | `@sonirotaru` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['focal_length_class: standard or short-telephoto (looks like a phone camera)'] | |
| 468 | `CzOTPgXxVMa` | `ref_384acc50` | `@sonirotaru` | `clean` | `no_action` |  | |
| 469 | `Cz3ulKBxWTi` | `ref_4d3b77a3` | `@sonirotaru` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: standard (looks like a point and shoot or early DSLR)'] | |
| 470 | `C0ZHOSmRVNw` | `ref_95152bf1` | `@sonirotaru` | `clean` | `no_action` |  | |
| 471 | `DAanFDjtfaY` | `ref_e4cb5933` | `@sonirotaru` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | training_style_tags=['texture']; materials_inline_literal_collapse | |
| 472 | `DUebF2ciHoj` | `ref_e5370148` | `@a.sound._` | `clean` | `no_action` |  | |
| 473 | `C5N_MojPGAX` | `ref_5eb9ee55` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: short-telephoto (likely 50mm-85mm equivalent for portrait)'] | |
| 474 | `C5bLAsHvspc` | `ref_5688d512` | `@clio1008` | `clean` | `no_action` |  | |
| 475 | `C5i8x4bypEB` | `ref_0ffa054d` | `@clio1008` | `clean` | `no_action` |  | |
| 476 | `C6EI4Miv2Jn` | `ref_fd58a1fb` | `@clio1008` | `clean` | `no_action` |  | |
| 477 | `C6IWXKGP_Df` | `ref_0625b9b3` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: short-telephoto (likely phone selfie or portrait lens)'] | |
| 478 | `C6K4nDvvCCa` | `ref_341eec2e` | `@clio1008` | `clean` | `no_action` |  | |
| 479 | `C6T9FOWvHhk` | `ref_d934c1c5` | `@clio1008` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | object_labels=['[']; materials_inline_literal_collapse | |
| 480 | `C6Y7_YtvFlH` | `ref_08065955` | `@clio1008` | `clean` | `no_action` |  | |
| 481 | `C6xcD9PPmd4` | `ref_d6f5e1d5` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: short-telephoto (likely phone camera, maybe 2x or 3x zoom)'] | |
| 482 | `C61jOG-v0k1` | `ref_d6e4b180` | `@clio1008` | `clean` | `no_action` |  | |
| 483 | `C630eCrv9bK` | `ref_16086c6f` | `@clio1008` | `clean` | `no_action` |  | |
| 484 | `C7EczXUPyQ6` | `ref_d6eeffb0` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['**coverage:** Upper body covered (vest/shirt)'] | |
| 485 | `C7qYb2Lvff1` | `ref_c1251d2d` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 486 | `C8hvPq3vils` | `ref_e70aaf21` | `@clio1008` | `clean` | `no_action` |  | |
| 487 | `C8mwi0yvsDX` | `ref_3855af50` | `@clio1008` | `clean` | `no_action` |  | |
| 488 | `C8t8MqqPDDF` | `ref_5b0a818d` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like phone camera)'] | |
| 489 | `C8_vWSAP5fs` | `ref_fc8301eb` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 490 | `C9ha1UPvBcs` | `ref_adb0e0a5` | `@clio1008` | `mixed` | `reparse_raw_with_hardened_stop_lines_and_nested_mapping_extractor_then_manual_diff_review` | materials={'material_type': 'material_type'}; materials_inline_literal_collapse | |
| 491 | `C9pnCEMPMSl` | `ref_5b161a5d` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse; evidence_note_key_leak=['* focal_length_class: "standard" or "short-telephoto" (looks like a phone or standard lens)'] | |
| 492 | `C-H8y0BPwQn` | `ref_de190f40` | `@clio1008` | `clean` | `no_action` |  | |
| 493 | `C-VPZR1v7q5` | `ref_59f7824c` | `@clio1008` | `clean` | `no_action` |  | |
| 494 | `C-czXKFvk1n` | `ref_375aabf4` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['* focal_length_class: standard or short-telephoto (looks like a portrait lens)'] | |
| 495 | `C-7h26Fvr1m` | `ref_c510f658` | `@clio1008` | `clean` | `no_action` |  | |
| 496 | `C_bDiMrzDJ4` | `ref_23b03b62` | `@clio1008` | `clean` | `no_action` |  | |
| 497 | `C_c9u9Gv3QD` | `ref_21e6d5fd` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | materials_inline_literal_collapse | |
| 498 | `DAVHrhFT7DL` | `ref_6ed961b1` | `@clio1008` | `clean` | `no_action` |  | |
| 499 | `DArXStuqRkF` | `ref_b669575e` | `@clio1008` | `field_collapse` | `reparse_raw_with_nested_mapping_extractor_then_review_coverage_pose_clothing` | evidence_note_key_leak=['focal_length_class: standard (looks like a phone or standard lens)'] | |
| 500 | `DAtIZKjK1xa` | `ref_a9c79581` | `@clio1008` | `clean` | `no_action` |  | |
