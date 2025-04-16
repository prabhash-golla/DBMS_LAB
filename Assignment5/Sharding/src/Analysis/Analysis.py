import requests
import time
import random  # May be used by PayloadGenerator
import numpy as np
import matplotlib.pyplot as plt
from payload_generator import PayloadGenerator

# Base URL for the server endpoints.
BASE_URL = "http://localhost:5000"


def plot_line_chart(x_values, y_values, x_label, y_label, title, path):
    """
    Plots and saves a line chart.
    
    Args:
        x_values (list or None): Values for the x-axis.
        y_values (list): Values for the y-axis.
        x_label (str): Label for the x-axis.
        y_label (str): Label for the y-axis.
        title (str): Title of the chart.
        path (str): File path where the chart image is saved.
    """
    plt.close()  # Close any existing plot.
    if x_values is None:
        plt.plot(y_values)
    else:
        plt.plot(x_values, y_values)
    plt.title(title)
    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.savefig(path)
    print(f"Saved plot: {title} to {path}")


def launch_rw_requests(low_idx, high_idx):
    """
    Launches a series of read and write requests to the server.
    
    The function creates a payload generator for request data, shuffles read/write
    endpoints, issues the requests, and times their execution.
    
    Args:
        low_idx (int): Lower bound index for generating payload.
        high_idx (int): Upper bound index for generating payload.
    
    Returns:
        tuple: A tuple of two lists containing the read times and write times.
    """
    generator = PayloadGenerator(low_idx, high_idx)
    num_rw = 100
    # Create list with 100 read endpoints and 100 write endpoints.
    endpoints = ["/read"] * num_rw + ["/write"] * num_rw

    read_times = []
    write_times = []
    
    for endpoint in endpoints:
        start = time.time()
        if endpoint == "/read":
            response = requests.post(
                BASE_URL + "/read",
                json=generator.generate_random_payload(endpoint="/read")
            )
            if response.status_code != 200:
                print("Error during read:", response.text)
            read_times.append(time.time() - start)
        elif endpoint == "/write":
            response = requests.post(
                BASE_URL + "/write",
                json=generator.generate_random_payload(endpoint="/write")
            )
            if response.status_code != 200:
                print("Error during write:", response.text)
            write_times.append(time.time() - start)

    return read_times, write_times


def subtask_a1():
    """
    Executes subtask A1 with the default configuration.
    
    It initializes the server with a given payload,
    launches read/write requests, prints summary timing information,
    and plots the read/write time charts.
    """
    payload = {
        "N": 3,
        "schema": {
            "columns": ["stud_id", "stud_name", "stud_marks"],
            "dtypes": ["Number", "String", "String"]
        },
        "shards": [
            {"stud_id_low": 0, "shard_id": "sh1", "shard_size": 4096},
            {"stud_id_low": 4096, "shard_id": "sh2", "shard_size": 4096},
            {"stud_id_low": 8192, "shard_id": "sh3", "shard_size": 4096}
        ],
        "servers": {
            "Server0": ["sh1", "sh2"],
            "Server1": ["sh2", "sh3"],
            "Server2": ["sh1", "sh3"]
        }
    }
    
    response = requests.post(BASE_URL + "/init", json=payload)
    if response.status_code != 200:
        print("Init Error in subtask A1:", response.text)
        return

    read_times, write_times = launch_rw_requests(0, 12000)

    print("A-1: Default Configuration")
    print("Total read time:", np.sum(read_times))
    print("Total write time:", np.sum(write_times))
    print("Average read time:", np.mean(read_times))
    print("Average write time:", np.mean(write_times))

    plot_line_chart(x_values=None, y_values=read_times,
                    x_label="Request", y_label="Time (s)",
                    title="Read Time", path="A1_read_time.png")
    plot_line_chart(x_values=None, y_values=write_times,
                    x_label="Request", y_label="Time (s)",
                    title="Write Time", path="A1_write_time.png")


def subtask_a2():
    """
    Executes subtask A2 with an extended default configuration.
    
    Similar to subtask A1, but uses a different payload that includes more servers,
    and then displays the performance of read/write operations.
    """
    payload = {
        "N": 9,
        "schema": {
            "columns": ["stud_id", "stud_name", "stud_marks"],
            "dtypes": ["Number", "String", "String"]
        },
        "shards": [
            {"stud_id_low": 0, "shard_id": "sh1", "shard_size": 4096},
            {"stud_id_low": 4096, "shard_id": "sh2", "shard_size": 4096},
            {"stud_id_low": 8192, "shard_id": "sh3", "shard_size": 4096}
        ],
        "servers": {
            "Server0": ["sh1", "sh2"],
            "Server1": ["sh2", "sh3"],
            "Server2": ["sh1", "sh3"],
            "Server3": ["sh1", "sh2"],
            "Server4": ["sh2", "sh3"],
            "Server5": ["sh1", "sh3", "sh2"],
            "Server6": ["sh1", "sh2", "sh3"],
            "Server7": ["sh2", "sh3", "sh1"],
            "Server8": ["sh1", "sh3"]
        }
    }
    
    response = requests.post(BASE_URL + "/init", json=payload)
    if response.status_code != 200:
        print("Init Error in subtask A2:", response.text)
        return

    read_times, write_times = launch_rw_requests(0, 12000)

    print("A-2: Default Configuration")
    print("Total read time:", np.sum(read_times))
    print("Total write time:", np.sum(write_times))
    print("Average read time:", np.mean(read_times))
    print("Average write time:", np.mean(write_times))

    plot_line_chart(x_values=None, y_values=read_times,
                    x_label="Request", y_label="Time (s)",
                    title="Read Time", path="A2_read_time.png")
    plot_line_chart(x_values=None, y_values=write_times,
                    x_label="Request", y_label="Time (s)",
                    title="Write Time", path="A2_write_time.png")


def subtask_a3():
    """
    Executes subtask A3 where the number of servers is varied.
    
    The function first initializes the server with two shards and two servers,
    then in a loop it launches read/write requests, collects timing statistics,
    and dynamically adds new servers and shards. Finally, it plots the mean,
    error, and total timings for reads and writes as the number of servers increases.
    """
    payload = {
        "N": 2,
        "schema": {
            "columns": ["stud_id", "stud_name", "stud_marks"],
            "dtypes": ["Number", "String", "String"]
        },
        "shards": [
            {"stud_id_low": 0, "shard_id": "sh1", "shard_size": 4096},
            {"stud_id_low": 4096, "shard_id": "sh2", "shard_size": 4096}
        ],
        "servers": {
            "Server0": ["sh1", "sh2"],
            "Server1": ["sh2", "sh1"]
        }
    }
    
    response = requests.post(BASE_URL + "/init", json=payload)
    if response.status_code != 200:
        print("Init Error in subtask A3:", response.text)
        return

    write_times = {}
    read_times = {}

    # Vary the number of servers from 2 to 9.
    for n in range(2, 10):
        r_times, w_times = launch_rw_requests(0, 21000)
        write_times[n] = {
            "total": np.sum(w_times),
            "mean": np.mean(w_times),
            "error": np.std(w_times)
        }
        read_times[n] = {
            "total": np.sum(r_times),
            "mean": np.mean(r_times),
            "error": np.std(r_times)
        }
        # Dynamically add new servers or shards based on n.
        if n == 2:
            payload_update = {
                "n": 1,
                "new_shards": [
                    {"stud_id_low": 8192, "shard_id": "sh3", "shard_size": 4096},
                    {"stud_id_low": 12288, "shard_id": "sh4", "shard_size": 4096},
                    {"stud_id_low": 16384, "shard_id": "sh5", "shard_size": 4096},
                    {"stud_id_low": 20480, "shard_id": "sh6", "shard_size": 4096}
                ],
                "servers": {f"Server{n}": ["sh1", "sh2", "sh3", "sh4", "sh5", "sh6"]}
            }
        elif n <= 7:
            payload_update = {
                "n": 1,
                "servers": {f"Server{n}": ["sh1", "sh2", "sh3", "sh4", "sh5", "sh6"]}
            }
        else:
            payload_update = {
                "n": 1,
                "servers": {f"Server{n}": ["sh3", "sh4", "sh5", "sh6"]}
            }
        
        response = requests.post(BASE_URL + "/add", json=payload_update)
        if response.status_code != 200:
            print("Error updating server configuration:", response.text)

    print("A-3: Varying Number of Servers")

    # Plot various performance metrics.
    plot_line_chart(
        x_values=list(write_times.keys()),
        y_values=[write_times[n]["mean"] for n in write_times],
        x_label="Number of Servers",
        y_label="Time (s)",
        title="Mean Write Time",
        path="A3_mean_write_time.png"
    )
    plot_line_chart(
        x_values=list(write_times.keys()),
        y_values=[write_times[n]["error"] for n in write_times],
        x_label="Number of Servers",
        y_label="Time (s)",
        title="Error Write Time",
        path="A3_error_write_time.png"
    )
    plot_line_chart(
        x_values=list(write_times.keys()),
        y_values=[write_times[n]["total"] for n in write_times],
        x_label="Number of Servers",
        y_label="Time (s)",
        title="Total Write Time",
        path="A3_total_write_time.png"
    )
    plot_line_chart(
        x_values=list(read_times.keys()),
        y_values=[read_times[n]["mean"] for n in read_times],
        x_label="Number of Servers",
        y_label="Time (s)",
        title="Mean Read Time",
        path="A3_mean_read_time.png"
    )
    plot_line_chart(
        x_values=list(read_times.keys()),
        y_values=[read_times[n]["error"] for n in read_times],
        x_label="Number of Servers",
        y_label="Time (s)",
        title="Error Read Time",
        path="A3_error_read_time.png"
    )
    plot_line_chart(
        x_values=list(read_times.keys()),
        y_values=[read_times[n]["total"] for n in read_times],
        x_label="Number of Servers",
        y_label="Time (s)",
        title="Total Read Time",
        path="A3_total_read_time.png"
    )


def main():
    """
    Main function to select and run a subtask based on user input.
    """
    try:
        selected_subtask = int(input("Enter subtask to run [1/2/3]: "))
    except ValueError:
        print("Invalid input. Please enter a number (1, 2, or 3).")
        return

    if selected_subtask == 1:
        subtask_a1()
    elif selected_subtask == 2:
        subtask_a2()
    elif selected_subtask == 3:
        subtask_a3()
    else:
        print("Invalid subtask number. Please run the script again with a valid subtask number (1, 2, or 3).")


if __name__ == "__main__":
    main()
