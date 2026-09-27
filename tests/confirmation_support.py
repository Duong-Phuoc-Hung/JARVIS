"""Test helper that performs the real one-use local confirmation protocol."""
def dispatch_confirmed(dispatcher, action, parameters, **kwargs):
    pending = dispatcher.dispatch_action(action, parameters, **kwargs)
    assert not pending.success
    assert pending.error_code == "CONFIRMATION_REQUIRED"
    token = pending.data["confirmation_token"]
    assert dispatcher.safety_interceptor.safety_gate.confirm(token)
    return dispatcher.dispatch_action(action, parameters, confirmation_token=token, **kwargs)


def confirm_latest_pending(dispatcher):
    gate = dispatcher.safety_interceptor.safety_gate
    pending = gate.get_latest_pending()
    assert pending is not None
    assert gate.confirm(pending.token)
    return dispatcher.dispatch_action(pending.payload["action_name"], pending.payload["parameters"], confirmation_token=pending.token)
