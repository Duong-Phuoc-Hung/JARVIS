# Final full-suite failures — fresh full-handoff run

45 failures remain. Isolated reruns do not erase this full-suite result.

## TEST_CONTRACT (22)

- `tests/e2e/test_tiers_1_to_4.py::test_r4_volume_and_brightness_adjustment`: Brightness backend is unavailable in this headless setup; assertion requires 75 instead of fail-closed None.

- `tests/e2e/test_v460_e2e.py::TestTier4RealWorldWorkflows::test_tier4_daily_routine_morning_to_focus_workflow`: shell_exec now requires SafetyGate confirmation; test expects immediate success.

- `tests/test_adversarial_challenger_1.py::test_r4_adversarial_volume_and_brightness_boundary_clamping`: Same unavailable brightness backend as #1; test expects clamp result without mocking a successful device write.

- `tests/test_adversarial_m3_challenger1.py::test_dashboard_cors_options_and_404_resilience`: Expects wildcard CORS despite current loopback origin policy.

- `tests/test_adversarial_m3_ui_app.py::test_dashboard_cors_and_options_and_404`: Expects wildcard CORS despite current loopback origin policy.

- `tests/test_adversarial_m4_challenger1.py::test_security_scanner_unauthenticated_biometric_rejection`: Labs gate rejects before biometric permission gate; fixture does not enable Labs.

- `tests/test_challenger2_stress.py::TestR5WebIntelligenceAdversarial::test_offline_network_failure_recovery_full_hub`: Briefing test expects speech_text; returned payload exposes weather_speech/news_speech. No live network was authorized.

- `tests/test_challenger2_stress.py::TestR8OverlayHUDAdversarial::test_long_text_truncation_and_turn_recording`: Test expects full 10k-character overlay text after production truncation.

- `tests/test_challenger_m1_2_empirical.py::test_record_audio_exception_resilience_when_sounddevice_fails`: Patches sounddevice.rec, but current capture path uses AudioEngine; 5-second capture is not proof of flaky timing.

- `tests/test_challenger_m4_2_security.py::test_scanner_and_capture_reject_unauthenticated_contexts`: Labs disabled preempts permission assertion.

- `tests/test_challenger_m4_2_security.py::test_packet_capture_injection_resilience[tcp and port 80; calc.exe]`: Labs disabled prevents the subprocess call expected by the injection fixture.

- `tests/test_challenger_m4_2_security.py::test_packet_capture_injection_resilience[udp | whoami]`: Labs disabled prevents the subprocess call expected by the injection fixture.

- `tests/test_challenger_m4_2_security.py::test_packet_capture_injection_resilience[host 10.0.0.1 && dir C:\\]`: Labs disabled prevents the subprocess call expected by the injection fixture.

- `tests/test_challenger_m4_2_security.py::test_packet_capture_injection_resilience[\`calc.exe\`]`: Labs disabled prevents the subprocess call expected by the injection fixture.

- `tests/test_challenger_m4_2_security.py::test_tshark_subprocess_timeout_or_error_handling`: Fixture expects packet_count on legacy capture result but receives gated ActionResult.

- `tests/test_empirical_challenger_m2.py::test_stress_cache_corruption_resilience_matrix[garbage_binary_200b]`: JARVIS_MOCK_AUDIO=1 deliberately bypasses WAV decoding/playback; corruption assertion is incompatible with that test environment.

- `tests/test_empirical_challenger_m2.py::test_stress_shell_plugin_timeout_and_privilege_enforcement`: SafetyGate confirmation preempts the expected shell timeout.

- `tests/test_m3_ux.py::test_startup_vocal_introduction`: First startup utterance is the briefing, while test expects the introduction as first utterance.

- `tests/test_plugins.py::test_plugin_shell_command_execution_tier1`: shell_exec now requires confirmation; test expects immediate execution.

- `tests/test_plugins.py::test_plugin_shell_timeout_error_handling_tier2`: shell_exec confirmation preempts timeout assertion.

- `tests/test_tier5_adversarial_sec_iot_comms_data.py::test_security_tshark_cli_parameters_and_bpf_injection`: Labs gate prevents expected TShark subprocess invocation.

- `tests/test_user_simulation.py::test_sim_18_cli_health_check_verification`: CLI output assertion expects old Operating System label; current health report format differs.

## CONFIRMED_CODE (5)

- `tests/e2e/test_tiers_1_to_4.py::test_r2_r3_vision_zero_size_roi_or_corrupt_bytes`: Zero-area ROI reaches JPEG encoder and raises ValueError; no zero-area guard before encoding.

- `tests/test_adversarial_sprint2_challenger1.py::TestAdversarialR2TTSCOMSafety::test_rapid_queue_flood_and_task_callback_exception_resilience`: TTS worker calls buggy callback a second time from except without guarding it; worker exits after 1/50 tasks.

- `tests/test_challenger2_autonomous_stress.py::TestR4ComputerUseVisionAndGUIActorAdversarial::test_negative_and_zero_screen_dimensions`: CoordinateMapper.pixel_to_norm uses truthiness for explicit zero dimensions and falls back to default screen size.

- `tests/test_challenger2_stress.py::TestR5WebIntelligenceAdversarial::test_malformed_rss_and_atom_xml_feeds`: RSS title passes through _clean_text (entity/whitespace only), retaining HTML markup that the plain-title assertion rejects.

- `tests/test_empirical_challenger_m3_2.py::test_welcome_pool_empty_and_whitespace_fallback`: Whitespace-only configured welcome list filters to an empty list, then random.choice raises IndexError.

## CONTRACT_REVIEW (16)

- `tests/test_adversarial_m1_diacritic_homophones.py::TestAdversarialStressAndReDoS::test_massive_string_dos_rejection_sla`: Long-input routing returns system_volume while this test expects unknown_intent. Reproduced; reconcile with contradictory long-input acceptance in #8.

- `tests/test_adversarial_m1_intent_router.py::TestAdversarialPunctuation::test_punctuation_tolerance[Jarvis, m\u1edf d\u1ef1 \xe1n: 'JARVIS-PRO'-workspace_prepare]`: Project-opening phrase resolves app_open instead of workspace_prepare; routing owner must reconcile current catalog precedence.

- `tests/test_adversarial_m1_intent_router.py::TestExtremeEdgeCases::test_huge_input_redos_resistance`: Long input is rejected as unknown_intent but this test expects workspace_prepare; do not blindly relax input guards.

- `tests/test_adversarial_m2_llm_router.py::test_pipeline_integration_category4_weather`: Weather pipeline assertion expects success; requires fixture/dispatcher tracing, not live credential use.

- `tests/test_adversarial_sprint2_challenger2.py::TestIntentRoutingAndReDoS::test_extensive_hardware_query_permutations_accented_and_unaccented`: Vietnamese memory query resolves generic_llm_response instead of hardware_telemetry_check.

- `tests/test_e2e_scenarios.py::test_e2e_tier3_unresponsive_app_healing_flow`: Healing workflow expects MockHardwareProvider RAM mutation that is not observed.

- `tests/test_e2e_scenarios.py::test_e2e_tier4_system_crisis_self_healing_workflow`: Crisis workflow expects MockHardwareProvider RAM mutation that is not observed.

- `tests/test_empirical_challenger_m2.py::test_stress_spotify_plugin_empty_and_corrupt_uris`: Spotify fixture expects success for empty/corrupt URI with no verified application result. Do not make runtime failure return success.

- `tests/test_empirical_challenger_m2_e2e_stress.py::test_e2e_full_pipeline_multi_pattern_audio_to_tts_queue`: Audio-to-gesture pipeline does not emit expected clap_pause_clap event; requires audio owner investigation.

- `tests/test_empirical_challenger_m3_2.py::test_app_log_interaction_delegation_and_custom_config`: Custom interaction log file is not created at the asserted path.

- `tests/test_empirical_challenger_m3_2.py::test_startup_intro_with_mocked_tts_queues_expected_phrase`: Startup emits briefing plus introduction; test expects one call. Confirm current startup contract.

- `tests/test_empirical_challenger_m3_2.py::test_startup_intro_custom_configured_phrase`: Startup emits two calls and test stops before validating configured startup phrase; requires separate contract review.

- `tests/test_user_simulation.py::test_sim_05_second_double_clap_triggers_ai_voice_loop`: Voice-loop fixture returns ndarray although production now requests CapturedAudio; no expected dispatched action is observed.

- `tests/test_user_simulation.py::test_sim_06_voice_loop_smart_keyword_home_assistant`: Voice-loop fixture returns ndarray although production now requests CapturedAudio; no expected HA action is observed.

- `tests/test_user_simulation.py::test_sim_07_voice_loop_smart_keyword_hardware_telemetry`: Voice-loop fixture returns ndarray although production now requests CapturedAudio; no expected telemetry action is observed.

- `tests/test_user_simulation.py::test_sim_16_vietnamese_smart_keyword_router_7_categories[kh\xf3a m\xe0n h\xecnh-system_power-action-lock-\u0110\xe3 kh\xf3a m\xe0n h\xecnh]`: Lock-screen phrase gets display-off response, differing from expected lock response.

## ORDER_TIMING_VARIABILITY (2)

- `tests/unit/test_runaway_hardening.py::TestDoubleClapFanoutOptIn::test_false_positive_repeated_double_clap_cannot_repeatedly_launch_fanout`: Global monotonic mock exhausted a finite timestamp list in the shared full-suite process.

- `tests/unit/test_sandbox_compat_fallback.py::TestCompatFallbackExplicitOptIn::test_unexpected_launcher_exception_never_falls_back_even_when_enabled`: Global Popen mock captured an unrelated PowerShell SMART-health query, not the expected sandbox launch. Shared-process background-work interference is evidenced by the captured call.
