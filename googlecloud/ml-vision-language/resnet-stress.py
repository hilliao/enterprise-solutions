import torch
import torchvision.models as models
import time


def run_inference_test():
    # Check if GPU is available
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"CUDA Version: {torch.version.cuda}")
        print(f"Initial GPU memory allocated: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB")
    else:
        print("WARNING: No GPU detected. This script is designed to test GPU usage.")
        return

    print("\nLoading pre-trained ResNet model...")
    # Load a pre-trained ResNet model (smaller than ResNet50)
    try:
        # For newer PyTorch versions
        model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    except TypeError:
        # For older PyTorch versions
        model = models.resnet18(pretrained=True)

    # Move the model to GPU
    model = model.to(device)

    # Set model to evaluation mode
    model.eval()

    # Create a batch of dummy input tensors (increasing batch size to stress GPU more)
    batch_size = 16
    dummy_input = torch.randn(batch_size, 3, 224, 224, device=device)

    print(f"Model loaded and moved to GPU")
    print(f"GPU memory allocated: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB")
    print("\nStarting inference loop... (press Ctrl+C to stop)")
    print("Check 'nvidia-smi' in another terminal to see GPU usage")

    try:
        iteration = 0
        start_time = time.time()

        while True:
            # Run inference with no gradients (faster)
            with torch.no_grad():
                output = model(dummy_input)

            # Process the output slightly to keep GPU active
            probabilities = torch.nn.functional.softmax(output, dim=1)

            # Count iterations and report progress
            iteration += 1

            if iteration % 10 == 0:
                elapsed = time.time() - start_time
                fps = iteration / elapsed
                print(f"\rCompleted {iteration} inference passes ({fps:.2f} FPS). "
                      f"GPU memory: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB", end="")

    except KeyboardInterrupt:
        print("\n\nInference stopped by user")
        elapsed = time.time() - start_time
        print(f"Ran {iteration} inference passes in {elapsed:.2f} seconds "
              f"({iteration / elapsed:.2f} FPS)")

    # Free up GPU memory
    del model
    del dummy_input
    torch.cuda.empty_cache()
    print("GPU memory cleared")


if __name__ == "__main__":
    run_inference_test()
