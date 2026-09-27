# Fresh base rerun classification

Snapshot `9d3c591`, same Python/CI environment. 45 failures reproduced; one candidate passed.
No baseline failure was fixed or suppressed by this task. Root-cause ownership still requires review.

## tests.e2e.test_tiers_1_to_4::test_r4_volume_and_brightness_adjustment

outside T-05/T-06/T-07; reproduced on base

```text
assert None == 75
```

## tests.e2e.test_tiers_1_to_4::test_r2_r3_vision_zero_size_roi_or_corrupt_bytes

outside T-05/T-06/T-07; reproduced on base

```text
ValueError: cannot write empty image as JPEG
```

## tests.e2e.test_v460_e2e.TestTier4RealWorldWorkflows::test_tier4_daily_routine_morning_to_focus_workflow

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert False is True
 +  where False = ActionResult(action_name='shell_exec', success=False, status=<ActionStatus.ERROR: 'ERROR'>, code='CONFIRMATION_REQUIRE...r_code='CONFIRMATION_REQUIRED', execution_time_ms=0.20490001770667732, requester='system', timestamp=1790489854.526672).success
```

## tests.test_adversarial_challenger_1::test_r4_adversarial_volume_and_brightness_boundary_clamping

outside T-05/T-06/T-07; reproduced on base

```text
assert None == 0
 +  where None = set_brightness(-50)
 +    where set_brightness = <jarvis.automation.control.ComputerController object at 0x000001BAA053DA90>.set_brightness
```

## tests.test_adversarial_m1_diacritic_homophones.TestAdversarialStressAndReDoS::test_massive_string_dos_rejection_sla

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 'system_volume' == 'unknown_intent'
  
  - unknown_intent
  + system_volume
```

## tests.test_adversarial_m1_intent_router.TestAdversarialPunctuation::test_punctuation_tolerance[Jarvis, m\u1edf d\u1ef1 \xe1n: 'JARVIS-PRO'-workspace_prepare]

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: Failed on noisy input: 'Jarvis, mở dự án: 'JARVIS-PRO'' -> got app_open
assert 'app_open' == 'workspace_prepare'
  
  - workspace_prepare
  + app_open
```

## tests.test_adversarial_m1_intent_router.TestExtremeEdgeCases::test_huge_input_redos_resistance

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 'unknown_intent' == 'workspace_prepare'
  
  - workspace_prepare
  + unknown_intent
```

## tests.test_adversarial_m2_llm_router::test_pipeline_integration_category4_weather

outside T-05/T-06/T-07; reproduced on base

```text
assert False is True
```

## tests.test_adversarial_m3_challenger1::test_dashboard_cors_options_and_404_resilience

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert None == '*'
 +  where None = get('Access-Control-Allow-Origin')
 +    where get = <http.client.HTTPMessage object at 0x000001BA9EC4EB10>.get
 +      where <http.client.HTTPMessage object at 0x000001BA9EC4EB10> = <http.client.HTTPResponse object at 0x000001BAFF86A3B0>.headers
```

## tests.test_adversarial_m3_ui_app::test_dashboard_cors_and_options_and_404

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert None == '*'
 +  where None = get('Access-Control-Allow-Origin')
 +    where get = <http.client.HTTPMessage object at 0x000001BA9F472BE0>.get
 +      where <http.client.HTTPMessage object at 0x000001BA9F472BE0> = <http.client.HTTPResponse object at 0x000001BA9F5D7C10>.headers
```

## tests.test_adversarial_m4_challenger1::test_security_scanner_unauthenticated_biometric_rejection

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert <ActionStatus...ABS_DISABLED'> == 'PERMISSION_DENIED'
  
  - PERMISSION_DENIED
  + LABS_DISABLED
```

## tests.test_adversarial_sprint2_challenger1.TestAdversarialR2TTSCOMSafety::test_rapid_queue_flood_and_task_callback_exception_resilience

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: Expected 50 tasks processed, got 1
assert 1 == 50
```

## tests.test_adversarial_sprint2_challenger2.TestIntentRoutingAndReDoS::test_extensive_hardware_query_permutations_accented_and_unaccented

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: Failed routing utterance 'kiểm tra bộ nhớ': got generic_llm_response, expected hardware_telemetry_check
assert False
```

## tests.test_challenger2_autonomous_stress.TestR4ComputerUseVisionAndGUIActorAdversarial::test_negative_and_zero_screen_dimensions

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: Tuples differ: (260, 463) != (0, 0)

First differing element 0:
260
0

- (260, 463)
+ (0, 0)
```

## tests.test_challenger2_stress.TestR5WebIntelligenceAdversarial::test_malformed_rss_and_atom_xml_feeds

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: 'Tiêu đề Test' not found in 'Tiêu đề <b>Test</b>'
```

## tests.test_challenger2_stress.TestR5WebIntelligenceAdversarial::test_offline_network_failure_recovery_full_hub

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: 'speech_text' not found in {'city': 'Hà Nội', 'weather': {'city': 'Hà Nội', 'temp_c': 27.0, 'feels_like_c': 29.0, 'condition': 'Nhiều mây', 'humidity': 75, 'wind_kph': 12.0, 'uv_index': None, 'pressure_hpa': None, 'visibility_km': None, 'source': 'offline_fallback', 'timestamp': 1790489861.3348448}, 'weather_speech': 'Thời tiết tại Hà Nội hiện tại là 27°C (cảm giác như 29°C), nhiều mây. Độ ẩm 75%, sức gió 12.0 km/h, thưa Ngài.', 'news': ['Nhiều bước tiến mới trong mô hình AI đa phương thức và Edge Computing (VnExpress)', 'Các tập đoàn công nghệ đẩy mạnh đầu tư hạ tầng bán dẫn và trung tâm dữ liệu (TechCrunch)', 'Phát triển trợ lý AI cá nhân trên máy tính cá nhân thu hút cộng đồng mã nguồn mở (VnExpress)'], 'news_articles': [{'title': 'Nhiều bước tiến mới trong mô hình AI đa phương thức và Edge Computing', 'link': 'https://vnexpress.net/so-hoa', 'description': 'Các công nghệ trí tuệ nhân tạo thế hệ mới đang được tối ưu hóa cho thiết bị biên.', 'published_at': '', 'source': 'VnExpress'}, {'title': 'Các tập đoàn công nghệ đẩy mạnh đầu tư hạ tầng bán dẫn và trung tâm dữ liệu', 'link': 'https://techcrunch.com', 'description': 'Thị trường chip bán dẫn tiếp tục ghi nhận nhu cầu mạnh mẽ.', 'published_at': '', 'source': 'TechCrunch'}, {'title': 'Phát triển trợ lý AI cá nhân trên máy tính cá nhân thu hút cộng đồng mã nguồn mở', 'link': 'https://vnexpress.net', 'description': 'Hệ sinh thái open-source phát triển mạnh mẽ cho desktop assistant.', 'published_at': '', 'sourc
```

## tests.test_challenger2_stress.TestR8OverlayHUDAdversarial::test_long_text_truncation_and_turn_recording

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: 'AAAA[228 chars]AAAAA...' != 'AAAA[228 chars]AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA[9718 chars]AAAA'
Diff is 10247 characters long. Set self.maxDiff to None to see it.
```

## tests.test_challenger_m1_2_empirical::test_record_audio_exception_resilience_when_sounddevice_fails

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: Fallback buffer generation took too long: 5.2513s
assert 5.25127710000379 < 0.1
```

## tests.test_challenger_m4_2_security::test_scanner_and_capture_reject_unauthenticated_contexts

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert <ActionStatus...ABS_DISABLED'> == 'PERMISSION_DENIED'
  
  - PERMISSION_DENIED
  + LABS_DISABLED
```

## tests.test_challenger_m4_2_security::test_packet_capture_injection_resilience[tcp and port 80; calc.exe]

outside T-05/T-06/T-07; reproduced on base

```text
assert 0 == 1
 +  where 0 = len([])
```

## tests.test_challenger_m4_2_security::test_packet_capture_injection_resilience[udp | whoami]

outside T-05/T-06/T-07; reproduced on base

```text
assert 0 == 1
 +  where 0 = len([])
```

## tests.test_challenger_m4_2_security::test_packet_capture_injection_resilience[host 10.0.0.1 && dir C:\\]

outside T-05/T-06/T-07; reproduced on base

```text
assert 0 == 1
 +  where 0 = len([])
```

## tests.test_challenger_m4_2_security::test_packet_capture_injection_resilience[`calc.exe`]

outside T-05/T-06/T-07; reproduced on base

```text
assert 0 == 1
 +  where 0 = len([])
```

## tests.test_challenger_m4_2_security::test_tshark_subprocess_timeout_or_error_handling

outside T-05/T-06/T-07; reproduced on base

```text
AttributeError: 'ActionResult' object has no attribute 'packet_count'
```

## tests.test_comms_hub::test_comms_telegram_photo_dispatch_tier1

outside T-05/T-06/T-07; reproduced on base

```text
assert False is True
```

## tests.test_e2e_scenarios::test_e2e_tier3_unresponsive_app_healing_flow

outside T-05/T-06/T-07; reproduced on base

```text
assert 93.0 < 80.0
 +  where 93.0 = <tests.conftest.MockHardwareProvider object at 0x000001BA9FE18D70>.ram_percent
```

## tests.test_e2e_scenarios::test_e2e_tier4_system_crisis_self_healing_workflow

outside T-05/T-06/T-07; reproduced on base

```text
assert 96.0 < 75.0
 +  where 96.0 = <tests.conftest.MockHardwareProvider object at 0x000001BA9FBAF390>.ram_percent
```

## tests.test_empirical_challenger_m1_stabilization::test_jarvis_app_concurrent_gesture_and_commands_stress

order/load sensitive candidate; not consistently reproduced

```text

```

## tests.test_empirical_challenger_m2::test_stress_cache_corruption_resilience_matrix[garbage_binary_200b]

outside T-05/T-06/T-07; reproduced on base

```text
assert True is False
```

## tests.test_empirical_challenger_m2::test_stress_spotify_plugin_empty_and_corrupt_uris

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert False is True
 +  where False = ActionResult(action_name='spotify_play', success=False, status=<ActionStatus.ERROR: 'ERROR'>, code='ACTION_FAILED', me...', error_code='ACTION_FAILED', execution_time_ms=0.04089999129064381, requester='system', timestamp=1790489871.3398473).success
```

## tests.test_empirical_challenger_m2::test_stress_shell_plugin_timeout_and_privilege_enforcement

outside T-05/T-06/T-07; reproduced on base

```text
assert ('timed out' in "hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa ngài. (mã xác nhận: f4a1ec68)" or 'CONFIRMATION_REQUIRED' == 'HANDLER_EXCEPTION'
 +  where "hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa ngài. (mã xác nhận: f4a1ec68)" = <built-in method lower of str object at 0x000001BA9FF38A50>()
 +    where <built-in method lower of str object at 0x000001BA9FF38A50> = "Hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa Ngài. (Mã xác nhận: F4A1EC68)".lower
 +      where "Hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa Ngài. (Mã xác nhận: F4A1EC68)" = ActionResult(action_name='shell_exec', success=False, status=<ActionStatus.ERROR: 'ERROR'>, code='CONFIRMATION_REQUIRE..._code='CONFIRMATION_REQUIRED', execution_time_ms=0.09520002640783787, requester='system', timestamp=1790489871.3503718).error
  
  - HANDLER_EXCEPTION
  + CONFIRMATION_REQUIRED)
```

## tests.test_empirical_challenger_m2_e2e_stress::test_e2e_full_pipeline_multi_pattern_audio_to_tts_queue

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 'clap_pause_clap' in ['action:spotify', 'action:chrome_claude', 'action:chrome_binance', 'double_clap', 'action:tts_welcome', 'action:cursor', ...]
```

## tests.test_empirical_challenger_m3_2::test_app_log_interaction_delegation_and_custom_config

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert False
 +  where False = exists()
 +    where exists = WindowsPath('C:/Users/MSI/.codex/worktrees/t05-t07-runtime-contracts/JARVIS/.task-tools/basetemp/pytest-of-MSI/pytest-0/test_app_log_interaction_deleg0/custom_app_interactions.log').exists
```

## tests.test_empirical_challenger_m3_2::test_welcome_pool_empty_and_whitespace_fallback

outside T-05/T-06/T-07; reproduced on base

```text
IndexError: Cannot choose from an empty sequence
```

## tests.test_empirical_challenger_m3_2::test_startup_intro_with_mocked_tts_queues_expected_phrase

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 2 == 1
 +  where 2 = len([('Chào buổi chiều thưa Ngài. Sau đây là bản tin tổng hợp hôm nay: Thời tiết tại Hà Nội hiện tại là 27°C (cảm giác như...n máy tính cá nhân thu hút cộng đồng mã nguồn mở.', False), ('Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.', False)])
```

## tests.test_empirical_challenger_m3_2::test_startup_intro_custom_configured_phrase

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 2 == 1
 +  where 2 = len([('Chào buổi chiều thưa Ngài. Sau đây là bản tin tổng hợp hôm nay: Thời tiết tại Hà Nội hiện tại là 27°C (cảm giác như...n máy tính cá nhân thu hút cộng đồng mã nguồn mở.', False), ('Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.', False)])
```

## tests.test_m3_ux::test_startup_vocal_introduction

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 'Hệ thống đã sẵn sàng, thưa Ngài. Tôi là JARVIS.' in 'Chào buổi chiều thưa Ngài. Sau đây là bản tin tổng hợp hôm nay: Thời tiết tại Hà Nội hiện tại là 27°C (cảm giác như 2...bán dẫn và trung tâm dữ liệu. Thứ 3: Phát triển trợ lý AI cá nhân trên máy tính cá nhân thu hút cộng đồng mã nguồn mở.'
```

## tests.test_plugins::test_plugin_shell_command_execution_tier1

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert False is True
 +  where False = ActionResult(action_name='shell_exec', success=False, status=<ActionStatus.ERROR: 'ERROR'>, code='CONFIRMATION_REQUIRE..._code='CONFIRMATION_REQUIRED', execution_time_ms=0.17030001617968082, requester='system', timestamp=1790489879.3849738).success
```

## tests.test_plugins::test_plugin_shell_timeout_error_handling_tier2

outside T-05/T-06/T-07; reproduced on base

```text
assert 'timed out' in "hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa ngài. (mã xác nhận: 464e525f)"
 +  where "hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa ngài. (mã xác nhận: 464e525f)" = <built-in method lower of str object at 0x000001BA9EB92F70>()
 +    where <built-in method lower of str object at 0x000001BA9EB92F70> = "Hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa Ngài. (Mã xác nhận: 464E525F)".lower
 +      where "Hành động 'shell_exec' yêu cầu xác nhận trước khi thực thi do có rủi ro cao, thưa Ngài. (Mã xác nhận: 464E525F)" = ActionResult(action_name='shell_exec', success=False, status=<ActionStatus.ERROR: 'ERROR'>, code='CONFIRMATION_REQUIRE...r_code='CONFIRMATION_REQUIRED', execution_time_ms=0.1345000055152923, requester='system', timestamp=1790489879.3950827).error
```

## tests.test_tier5_adversarial_sec_iot_comms_data::test_security_tshark_cli_parameters_and_bpf_injection

outside T-05/T-06/T-07; reproduced on base

```text
assert 0 == 1
 +  where 0 = len([])
```

## tests.test_tier5_adversarial_sec_iot_comms_data::test_telegram_unauthorized_user_and_injection_defense

outside T-05/T-06/T-07; reproduced on base

```text
assert 503 == 200
```

## tests.test_user_simulation::test_sim_05_second_double_clap_triggers_ai_voice_loop

outside T-05/T-06/T-07; reproduced on base

```text
assert False
 +  where False = _wait_for_condition(<function test_sim_05_second_double_clap_triggers_ai_voice_loop.<locals>.<lambda> at 0x000001BAA00CF9C0>, timeout=3.0)
```

## tests.test_user_simulation::test_sim_06_voice_loop_smart_keyword_home_assistant

outside T-05/T-06/T-07; reproduced on base

```text
assert False
 +  where False = _wait_for_condition(<function test_sim_06_voice_loop_smart_keyword_home_assistant.<locals>.<lambda> at 0x000001BAA00CFC40>, timeout=3.0)
```

## tests.test_user_simulation::test_sim_07_voice_loop_smart_keyword_hardware_telemetry

outside T-05/T-06/T-07; reproduced on base

```text
assert False
 +  where False = _wait_for_condition(<function test_sim_07_voice_loop_smart_keyword_hardware_telemetry.<locals>.<lambda> at 0x000001BAA01D6FC0>, timeout=3.0)
```

## tests.test_user_simulation::test_sim_16_vietnamese_smart_keyword_router_7_categories[kh\xf3a m\xe0n h\xecnh-system_power-action-lock-\u0110\xe3 kh\xf3a m\xe0n h\xecnh]

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 'đã khóa màn hình' in 'đang tắt màn hình cho ngài.'
 +  where 'đã khóa màn hình' = <built-in method lower of str object at 0x000001BA9F210CE0>()
 +    where <built-in method lower of str object at 0x000001BA9F210CE0> = 'Đã khóa màn hình'.lower
 +  and   'đang tắt màn hình cho ngài.' = <built-in method lower of str object at 0x000001BAFFB69CB0>()
 +    where <built-in method lower of str object at 0x000001BAFFB69CB0> = 'Đang tắt màn hình cho Ngài.'.lower
 +      where 'Đang tắt màn hình cho Ngài.' = IntentResult(action_name='system_power', parameters={'action': 'screen_off'}, confidence=1.0, source='rule_fallback', ... response_text='Đang tắt màn hình cho Ngài.', requires_confirmation=False, confirmation_prompt=None, danger_level=None).response_text
```

## tests.test_user_simulation::test_sim_18_cli_health_check_verification

outside T-05/T-06/T-07; reproduced on base

```text
AssertionError: assert 'Operating System:' in '=================================================================\n JARVIS System Health Diagnostics (v5.2.1)\n======...==========================\n Diagnostics completed. Browser automation is READY; review each subsystem result above.\n'
```

