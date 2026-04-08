import sys
import types
import unittest


def _install_test_stubs() -> None:
    torch_stub = types.ModuleType("torch")
    torch_stub.cuda = types.SimpleNamespace(is_available=lambda: False)
    torch_stub.dtype = type("dtype", (), {})
    torch_stub.float16 = object()
    torch_stub.bfloat16 = object()
    torch_stub.float32 = object()

    pil_stub = types.ModuleType("PIL")
    pil_stub.__path__ = []  # type: ignore[attr-defined]
    pil_image_stub = types.ModuleType("PIL.Image")
    pil_image_stub.Image = type("Image", (), {})
    pil_stub.Image = pil_image_stub

    transformers_stub = types.ModuleType("transformers")
    for name in (
        "AutoProcessor",
        "AutoTokenizer",
        "BitsAndBytesConfig",
        "BlipForConditionalGeneration",
        "BlipProcessor",
        "GitForCausalLM",
        "VisionEncoderDecoderModel",
        "ViTImageProcessor",
    ):
        setattr(transformers_stub, name, type(name, (), {}))

    sys.modules.setdefault("torch", torch_stub)
    sys.modules.setdefault("PIL", pil_stub)
    sys.modules.setdefault("PIL.Image", pil_image_stub)
    sys.modules.setdefault("transformers", transformers_stub)


_install_test_stubs()

from src.contracts.vlm import build_vlm_error_result


class VlmContractErrorHandlingTestCase(unittest.TestCase):
    def test_build_vlm_error_result_handles_unknown_model_key(self) -> None:
        result = build_vlm_error_result(
            request_id="req-1",
            user_id="user-1",
            image_key="captures/sample.jpg",
            error=RuntimeError("boom"),
            model_key="unknown-model",
            quantization="none",
            dtype_name="float16",
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["providerMetadata"]["modelKey"], "unknown-model")
        self.assertEqual(result["providerMetadata"]["modelId"], "unknown-model")
        self.assertIsNone(result["providerMetadata"]["modelFamily"])

    def test_build_vlm_error_result_accepts_explicit_error_policy(self) -> None:
        result = build_vlm_error_result(
            request_id="req-2",
            user_id="user-2",
            image_key="captures/sample.jpg",
            error=RuntimeError("timeout"),
            model_key="unknown-model",
            quantization="none",
            dtype_name="float16",
            error_code="inference_timeout",
            retryable=True,
        )

        self.assertEqual(result["errorCode"], "inference_timeout")
        self.assertTrue(result["retryable"])


if __name__ == "__main__":
    unittest.main()
