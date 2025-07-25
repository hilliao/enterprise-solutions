import torch
import torchvision.models as models
import time
import argparse

def run_gpu_stress_test(target_memory_mb):
    """
    Runs a GPU stress test by loading a model and allocating a specific
    amount of memory as defined by the user.
    
    Args:
        target_memory_mb (int): The target GPU memory to allocate in megabytes.
    """
    # Check if GPU is available
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    if device.type != "cuda":
        print("WARNING: No GPU detected. This script requires a CUDA-enabled GPU.")
        return

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"CUDA Version: {torch.version.cuda}")
    print(f"Initial GPU memory allocated: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB")

    print("\nLoading pre-trained ResNet50 model...")
    try:
        model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
    except TypeError:
        model = models.resnet50(pretrained=True)

    model = model.to(device)
    model.eval()
    print(f"Model loaded. Memory allocated for model: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB")

    # --- Allocate a large tensor to reach the target memory usage ---
    try:
        current_memory_bytes = torch.cuda.memory_allocated(0)
        # Convert target MB to bytes
        target_memory_bytes = target_memory_mb * (1024 ** 2)

        if target_memory_bytes > current_memory_bytes:
            bytes_to_allocate = target_memory_bytes - current_memory_bytes
            elements_to_allocate = int(bytes_to_allocate / 4) # float32 is 4 bytes
            print(f"\nAllocating a large tensor to reach ~{target_memory_mb} MB of memory...")
            stress_tensor = torch.randn(elements_to_allocate, device=device)
            print(f"Stress tensor allocated. Total GPU memory now: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB")
        else:
            stress_tensor = None
            print("\nModel already exceeds target memory. No stress tensor needed.")

    except torch.cuda.OutOfMemoryError:
        print("\nERROR: Out of memory. Your GPU does not have enough free memory to allocate the stress tensor.")
        print(f"Try reducing the '--mem' value below {target_memory_mb} or closing other applications using the GPU.")
        del model
        torch.cuda.empty_cache()
        return

    # Batch size is kept relatively small to avoid OOM during inference itself
    batch_size = 32
    dummy_input = torch.randn(batch_size, 3, 224, 224, device=device)

    print(f"\nStarting inference loop with batch size {batch_size}... (press Ctrl+C to stop)")
    print("Check 'nvidia-smi' in another terminal to monitor GPU usage.")

    try:
        iteration = 0
        start_time = time.time()
        while True:
            with torch.no_grad():
                output = model(dummy_input)
            
            probabilities = torch.nn.functional.softmax(output, dim=1)

            iteration += 1
            if iteration % 10 == 0:
                elapsed = time.time() - start_time
                fps = iteration / elapsed
                print(f"\rCompleted {iteration} inference passes ({fps:.2f} FPS). "
                      f"GPU memory: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB", end="")

    except KeyboardInterrupt:
        print("\n\nInference stopped by user.")
        elapsed = time.time() - start_time
        if elapsed > 0:
            print(f"Ran {iteration} inference passes in {elapsed:.2f} seconds ({iteration / elapsed:.2f} FPS).")

    except torch.cuda.OutOfMemoryError:
        print("\n\nERROR: Out of memory during inference.")
        print("Your GPU might not have enough memory to handle the model's computations with this batch size.")
        print("Try reducing the 'batch_size' or '--mem' value.")

    finally:
        print("\nClearing GPU memory...")
        del model
        del dummy_input
        if 'stress_tensor' in locals() and stress_tensor is not None:
            del stress_tensor
        torch.cuda.empty_cache()
        print(f"Final GPU memory allocated: {torch.cuda.memory_allocated(0) / 1024 ** 2:.2f} MB")
        print("GPU memory cleared.")

def main():
    """Parses command-line arguments and runs the GPU stress test."""
    parser = argparse.ArgumentParser(
        description="GPU Stress Test with Custom Memory Allocation.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--mem',
        type=int,
        default=2200,
        help="Target GPU memory to allocate in MB.\nExample: --mem 3500 (for 3500MB)\n(default: 2200 MB)"
    )
    args = parser.parse_args()

    run_gpu_stress_test(args.mem)

if __name__ == "__main__":
    main()
