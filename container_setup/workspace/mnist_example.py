import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets, transforms
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt
import os
from logger import Log, LogLevel

Log.set_log_file("/workspace/logs")
Log.set_console_output(True)
Log.v("mnist_example.py start")

# GPU 사용 여부 확인
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
Log.v(f"device: {device}")

# 데이터 전처리 및 로딩
transform = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize((0.1307,), (0.3081,))
])

train_dataset = datasets.MNIST(
    root='./data', train=True, download=True, transform=transform)
test_dataset = datasets.MNIST(
    root='./data', train=False, download=True, transform=transform)

train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=1000, shuffle=False)
Log.v("loaded dataset")

# 간단한 CNN 모델 정의


class SimpleCNN(nn.Module):
    def __init__(self):
        super(SimpleCNN, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, 1)
        self.conv2 = nn.Conv2d(32, 64, 3, 1)
        self.fc1 = nn.Linear(64 * 24 * 24, 128)
        self.fc2 = nn.Linear(128, 10)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(0.25)

    def forward(self, x):
        x = self.relu(self.conv1(x))
        x = self.relu(self.conv2(x))
        x = torch.flatten(x, 1)
        x = self.dropout(self.relu(self.fc1(x)))
        x = self.fc2(x)
        return x


model = SimpleCNN().to(device)
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters())  # type: ignore

save_path = './models/latest.pt'
save_dir = os.path.dirname(save_path)
if not os.path.exists(save_dir): os.makedirs(save_dir, exist_ok=True)

train_losses = []
test_losses = []
test_accuracies = []

# 학습 함수


def train(model, loader, optimizer, criterion, epoch):
    model.train()
    running_loss = 0.0
    for batch_idx, (data, target) in enumerate(loader):
        data, target = data.to(device), target.to(device)
        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()

        running_loss += loss.item()
        if batch_idx % 100 == 0:
            Log.i(
                f'Train Epoch: {epoch} [{batch_idx * len(data)}/{len(loader.dataset)}]\tLoss: {loss.item():.6f}')
    avg_loss = running_loss / len(train_loader)
    train_losses.append(avg_loss)
    Log.i(f"Train Epoch: {epoch} Agverage loss: {avg_loss:.6f}")


# 평가 함수
def test(model, loader, criterion):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += criterion(output, target).item()
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()

    test_loss /= len(loader)
    accuracy = 100. * correct / len(loader.dataset)
    test_losses.append(test_loss)
    test_accuracies.append(accuracy)
    Log.i(f'Test set: Average loss: {test_loss:.4f}, Accuracy: {correct}/{len(loader.dataset)} ({accuracy:.2f}%)')


def save_loss_graph(epoch):
    fig, ax1 = plt.subplots()

    epochs = range(1, epoch + 1)

    # 왼쪽 Y축: Train/Test Loss
    ax1.set_xlabel("Epoch")
    ax1.set_ylabel("Loss", color='black')
    ax1.plot(epochs, train_losses, label="Train Loss",
             color='orange', marker='o', linestyle='-')
    ax1.plot(epochs, test_losses, label="Test Loss",
             color='blue', marker='o', linestyle='-')
    ax1.tick_params(axis='y', labelcolor='black')
    ax1.grid(True)

    # 오른쪽 Y축: Test Accuracy
    ax2 = ax1.twinx()
    ax2.set_ylabel("Test Accuracy (%)", color='green')
    ax2.plot(epochs, test_accuracies, label="Test Accuracy",
             color='green', marker='s', linestyle='--')
    ax2.tick_params(axis='y', labelcolor='green')

    # 범례 두 축 병합 표시
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')

    plt.title("Loss & Accuracy Over Epochs")
    plt.tight_layout()
    plt.savefig("logs/train_loss.png")
    plt.close()


# 학습 및 테스트 루프
learn_step = Log.start("training")
for epoch in range(1, 21):  # 20 에폭
    train(model, train_loader, optimizer, criterion, epoch)
    test(model, test_loader, criterion)
    torch.save(model.state_dict(), save_path)
    # subprocess.run("/root/DOLAB/sync.sh")
Log.end(learn_step)
# subprocess.run("/root/DOLAB/terminate.sh")
