import docker

client = docker.from_env()

result = client.containers.run(
    "python-sandbox",
    ["python", "-c", "print('Hello from Docker!')"],
    remove=True,
    stdout=True,
    stderr=True
)
print(result.decode())