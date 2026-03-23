# ai-services/src/rl/train_rl_model.py
"""
Training script for the PPO RL traffic signal controller.

Usage:
  python train_rl_model.py                     # Full 200k training
  python train_rl_model.py --timesteps 10000   # Quick smoke test
  python train_rl_model.py --evaluate          # Evaluate saved model (10 episodes)
"""

import argparse
import os
import sys

# Add parent src dir to path so we can import traffic_env
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import EvalCallback
    from stable_baselines3.common.monitor import Monitor
except ImportError:
    print("ERROR: stable-baselines3 not installed.")
    print("Run: pip install stable-baselines3")
    sys.exit(1)

from rl.traffic_env import TrafficSignalEnv

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_SAVE   = os.path.join(BASE_DIR, "models", "weights", "rl_signal")
LOG_TRAIN    = os.path.join(BASE_DIR, "logs", "rl_training")
LOG_EVAL     = os.path.join(BASE_DIR, "logs", "rl_eval")
LOG_TB       = os.path.join(BASE_DIR, "logs", "tensorboard")


def _make_dirs() -> None:
    for path in [MODEL_SAVE, LOG_TRAIN, LOG_EVAL, LOG_TB]:
        os.makedirs(path, exist_ok=True)


def train(total_timesteps: int) -> None:
    _make_dirs()

    # Training environment wrapped in Monitor for episode stats
    train_env = Monitor(TrafficSignalEnv(), filename=os.path.join(LOG_TRAIN, "monitor.csv"))

    # Separate eval environment (never used for training)
    eval_env = Monitor(TrafficSignalEnv())

    model = PPO(
        "MlpPolicy",
        train_env,
        verbose=1,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.95,
        clip_range=0.2,
        tensorboard_log=LOG_TB,
    )

    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=MODEL_SAVE,
        log_path=LOG_EVAL,
        eval_freq=5000,
        deterministic=True,
        render=False,
    )

    print(f"Starting PPO training for {total_timesteps:,} timesteps...")
    model.learn(total_timesteps=total_timesteps, callback=eval_callback)

    final_path = os.path.join(MODEL_SAVE, "final_model")
    model.save(final_path)
    print(f"\nTraining complete. Model saved to {MODEL_SAVE}/")
    print(f"  best_model.zip  ← used by inference engine")
    print(f"  final_model.zip ← final checkpoint")


def evaluate(n_episodes: int = 10) -> None:
    best_model_path = os.path.join(MODEL_SAVE, "best_model.zip")
    if not os.path.exists(best_model_path):
        print(f"ERROR: No saved model found at {best_model_path}")
        print("Run training first: python train_rl_model.py")
        sys.exit(1)

    model = PPO.load(best_model_path)
    env   = TrafficSignalEnv()

    rewards = []
    for ep in range(n_episodes):
        obs, _ = env.reset()
        ep_reward = 0.0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(int(action))
            ep_reward += reward
            done = terminated or truncated
        rewards.append(ep_reward)
        print(f"  Episode {ep+1:2d}: reward = {ep_reward:.1f}")

    mean_r = sum(rewards) / len(rewards)
    print(f"\nMean reward over {n_episodes} episodes: {mean_r:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RL traffic signal training")
    parser.add_argument(
        "--timesteps", type=int, default=200_000,
        help="Total training timesteps (default: 200000)"
    )
    parser.add_argument(
        "--evaluate", action="store_true",
        help="Skip training and evaluate saved best_model over 10 episodes"
    )
    args = parser.parse_args()

    if args.evaluate:
        evaluate()
    else:
        train(args.timesteps)


if __name__ == "__main__":
    main()
