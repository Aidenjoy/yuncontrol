from yunwork_cloud.identity import instance_id_for, valid_instance_id


def test_instance_ids_are_stable_opaque_and_distinct():
    secret = "test-secret-that-is-long-enough-for-hmac"
    first = instance_id_for("ut-user:中文/名字", secret)
    assert first == instance_id_for("ut-user:中文/名字", secret)
    assert first != instance_id_for("ut-user:another", secret)
    assert first != instance_id_for("ut-user:中文/名字", secret + "different")
    assert valid_instance_id(first)
    assert "中文" not in first and "/" not in first
    assert not valid_instance_id("../user-000000000000000000000000")
