from canospar.runtime.profile import RuntimeProfile


def test_runtime_profile_contains_execution_only_fields() -> None:
    profile = RuntimeProfile(
        profile_id="server-a",
        cpu_count=16,
        ram_gib=90.0,
        gpu_count=1,
        container_runtime="native",
        scheduler="local",
        transport="ssh",
        server_class="linux",
    )

    assert profile.gpu_count == 1
    assert profile.transport == "ssh"
