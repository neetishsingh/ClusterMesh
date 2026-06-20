"""Submit a remote task to connected agents."""

from mesh.driver.cluster import DriverCluster
from mesh.driver.job_manager import JobManager
from mesh.driver.server import DriverServer
import mesh.tasks.builtins  # noqa: F401


def main() -> None:
    cluster = DriverCluster()
    manager = JobManager(cluster=cluster)
    server = DriverServer(cluster=cluster, job_manager=manager)
    server.start()

    print("Driver running. Connect agents, then press Enter to submit a job...")
    input()

    if not cluster.live_nodes():
        print("No agents connected!")
        server.stop()
        return

    print(f"Cluster: {len(cluster.live_nodes())} node(s)")
    result = manager.submit_remote_by_name("builtin.counter", total_work=200, timeout=30)
    print(f"Result: {result}")
    server.stop()


if __name__ == "__main__":
    main()
