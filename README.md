# 8Knot

![Pre-Commit](https://github.com/chaoss/8Knot/actions/workflows/pre-commit.yml/badge.svg)
![Build-Push](https://github.com/chaoss/8Knot/actions/workflows/build-push-quay.yml/badge.svg)
![Docker Compose](https://github.com/chaoss/8Knot/actions/workflows/docker-compose-build.yml/badge.svg)

Welcome to 8Knot!

## [Example of Application](https://eightknot.osci.io/)

## Introduction

8Knot is a [Dash](https://dash.plotly.com/) data web-app built by Red Hat's Open Source Program Office ([OSPO](https://www.redhat.com/en/blog/channel/red-hat-open-source-program-office)).

The number of repositories and projects that GitHub hosts is staggering. Even more impressive is the rate at which this number is growing.
Projects on GitHub range from student projects to technological monoliths like the
Linux Kernel. Understanding the growth trajectory, contributor behavior, progress blockers, etc. intuitively is no longer feasible for individual
large projects, and is even less so for groups of projects. It is necessary that community architects and contributors alike have an accessible,
correct, and extendable resource that can aggregate and interpret the data describing these communities.

The goal of this application is to serve Open Source community mangers, stakeholders, contributors, and enthusiasts by
providing an insightful and convenient interface to the Open Source project data set collected by the project [Augur](https://github.com/chaoss/augur) (CHAOSS).

---

## Contributing

Please see our guide to contributing to this project at the following site: [CONTRIBUTORS.md](docs/CONTRIBUTORS.md)

Once you've read that, please follow our guidance on how to add additional figures and pages to the application: [new_viz_guidance.md](/docs/new_viz_guidance.md)

---

## Application File Structure

The file-structure of our application is intuitive. Non-application files are omitted from this overview:

<pre>
8Knot
+-- pages/
    |   +-- index/
               |     +-- index_callbacks.py
               |     +-- index_layout.py
        +-- welcome/
               |     +-- welcome.py
               |     +-- visualizations/
                            |     +-- name_of_visualization_1.py
                            |     ...
                            |     +-- name_of_visualization_n.py
        +-- contributions/
               |     +-- contributions.py
               |     +-- visualizations/
                            |     ...
        +-- contributors/
               |     +-- cntrb_behavior.py
               |     +-- cntrb_type.py
               |     +-- visualizations/
                            |     ...
        +-- chaoss/
               |     +-- chaoss.py
               |     +-- visualizations/
                            |     ...
        +-- affiliation/
               |     +-- affiliation.py
               |     +-- visualizations/
                            |     ...
        +-- codebase/
               |     +-- codebase.py
               |     +-- visualizations/
                            |     ...
        +-- visualization_template/
               |     +-- viz_template.py
        +-- utils/
+-- app.py
+-- _celery.py
+-- _login.py
+-- _bots.py
.
.
.
+-- ~other files~
</pre>

The application 'Dash' instance is defined in the 'app.py' file, as is the app.server object that our WSGI server uses, and the manager for the task-queue.

The 'Dash' application instance imports the application's base layout from the '/pages/index/index_layout.py' file. The logic to process user input to components is laid out in this file (search bar, page selectors) is defined in '/pages/index/index_callbacks.py.'

Each page of the application is in its own 'pages' folder. On each page a variety of metrics and figures are rendered. These, for each page, are in the 'page_name/visualizations/' folder, and are imported into the file 'page_name.py.'

If one were to add a figure or a metric to a page, they would add it to that page's 'visualizations' folder and import the visualization into the page's respective 'page_name.py' file.

---

## Motivations and Augur

Open Source software is everywhere, yet it is difficult to find data about Open Source projects. Project community managers, advocates, contributors, and enthusiasts ought to be able to see high-level behavioral, health, and growth trends in their repository that assist their own intuition.

Augur, a project in the [CHAOSS](https://chaoss.community) Foundation, is closing this gap by collecting structured data about Free and Open Source Software (FOSS).

Quoting Augur's own README.md:

> "Augur’s main focus is to measure the overall health and sustainability of open source projects, as these types of projects are system critical for nearly every software organization or company.
> We do this by gathering data about project repositories and normalizing that into our data model to provide useful metrics about your project’s health."

8Knot's contribution to further closing this gap is to provide an interface to the data collected and organized by Augur as a data web-app with both essential statistical figures,
and higher-order machine learning and data science-informed insights.

---

## State of Development

In the insightful words of Karl Fogel from his book "Producing Open Source Software":

> "This is alpha software with known bugs. It runs, and works at least some of the time, but use at your own risk."

We are incredibly happy to have people try our application in any state, and we doubly welcome any thorough bug reports.
We would seriously recommend, however, that any conclusions drawn from this app, either realized from our deployed application or
from a local instance, be scrutinized heavily until we make a proper, stable, >1.0 release.

---

## Communication

Please feel free to join our CHAOSS Slack Channel (#wg-augur-8knot) for more information on 8Knot and Augur!

We would prefer any initial communication be through Matrix but if you would prefer to talk to one of our maintainers, please feel free to peruse our [AUTHORS.md](docs/AUTHORS.md) file where you can find contact details.

---

## Usage Examples

If you would like to see the current state of our application, we would love any user-stories or bug-reports from visiting our alpha-deployment!

[8Knot](https://eightknot.osci.io/)

If you would prefer to look at our most up-to-date work, please check out the following section.

---

## Architectural Comment

Our demonstration application run in Oregon (AWS us-west2), while the Augur database that we use is in Columbus, MO. To improve user experience,
we implement a cache using PostgreSQL as a side-car to our application.

This has added significant application complexity that will be rebuilt and removed in the near future once we've replication our Augur database
to the same data-center as our application.

If you experience trouble with the existing caching architecture, please log an issue or reach out to us directly.

---

## Deploying 8Knot Locally and for Development

We've tried to make it as easy as possible to run your own 8Knot instance.

### Credentials

You will need credentials of the following form, named `.env`, at the top-level of the 8Knot directory that you clone.

A sample file illustrating the format is available in `.env.sample` that can be copy-pasted and renamed to `.env` to get you started with a basic set of valid credentials.

These credentials are suitable for development, but please replace any secrets with different values in production.

8Knot doesn't handle user accounts or data collection requests on its own. To support these features, you'll need to add the
following additional configuration to your `.env` file.

Setting the `DEBUG_8KNOT` environmental variable to True will enable hot reloading of the Dash application, after any change to a file inside the 8Knot/ directory.

You'll need to register your 8Knot instance with an Augur front-end application to get an `AUGUR_APP_ID` and an `AUGUR_CLIENT_SECRET`.
All parameters wrapped in `< >` will need to be replaced below. `<endpoint>` variables refer to the host of the Augur front-end that
you're using.

8Knot uses these parameters to manage user accounts via an OAuth2.0 flow, so user passwords are never handled directly.

```
    AUGUR_LOGIN_ENABLED=True
    AUGUR_APP_ID=<id>
    AUGUR_CLIENT_SECRET=<secret>
    AUGUR_SESSION_GENERATE_ENDPOINT=<endpoint>/api/unstable/user/session/generate
    AUGUR_USER_GROUPS_ENDPOINT=<endpoint>/api/unstable/user/groups/repos?columns=repo_id,repo_git
    AUGUR_USER_ACCOUNT_ENDPOINT=<endpoint>/account/settings
    AUGUR_USER_AUTH_ENDPOINT=<endpoint>/user/authorize?client_id=<AUGUR_APP_ID>response_type=code
    AUGUR_ADMIN_NAME_ENDPOINT=<endpoint>/api/unstable/application/
    AUGUR_ADMIN_GROUP_NAMES_ENDPOINT=<endpoint>/api/unstable/application/groups/names
    AUGUR_ADMIN_GROUPS_ENDPOINT=<endpoint>/api/unstable/application/group/repos
    OAUTH_CLIENT_NAME=augur
    OAUTH_CLIENT_ID=<id>
    OAUTH_CLIENT_SECRET=<secret>
    OAUTH_AUTHORIZE_URL=<endpoint>/user/authorize
    OAUTH_TOKEN_URL=<endpoint>/api/unstable/user/session/generate
    OAUTH_REDIRECT_URI = localhost:8080/
```

Note: You'll have to manually fill in the \<AUGUR_APP_ID\> in the AUGUR_USER_AUTH_ENDPOINT environment variable.

In-depth instructions for enabling 8Knot + Augur integration is available in [AUGUR_LOGIN.md](docs/AUGUR_LOGIN.md).
An overview of OAuth's implementation in 8Knot can be found here: [user-accounts-in-8knot.md](docs/user-accounts-in-8knot.md).


### Runtime

We use containers to minimize the installation requirements for development and single-machine production deployments. If you do not have Docker on your system, please follow the following guide: [Install Docker](https://docs.docker.com/engine/install)

We use Docker's Compose feature to spin up all application resources together. Please make sure you have Docker Compose installed on your system. You can find documentation on doing so here: [Docker Compose](https://docs.docker.com/compose/install)


#### Option 1: Using Podman (Recommended)

1. **If transitioning from Docker Desktop**
   - Uninstall Docker Desktop (requires GUI uninstall and checking for remnants)
   - Remove any remaining Docker files/configurations. Further information on this below.

2. **Install Podman:**
   - On macOS: `brew install podman podman-desktop`
   - On Linux: Follow the [official installation guide](https://podman.io/getting-started/installation)

3. **Initial Setup:**
   - On macOS: Initialize and start a Podman machine:
     ```bash
     podman machine init
     podman machine start
     ```
   - Install docker-compose (used by Podman Compose):
     ```bash
     brew install docker-compose  # on macOS
     # or use your system's package manager
     ```

4. **Verify Installation:**
   ```bash
   podman --version
   podman compose --version
   ```

5. **Install Podman Desktop. This is optional but recommended.**

#### Using Podman

If you're using Podman, you can use either `podman compose` or `docker compose` (thanks to the compatibility layer). Here are both options:

Using podman-compose directly:
```bash
# Start the application
podman compose up --build

# Scale worker pools (recommended)
podman compose up --build --scale worker-query=2 --scale worker-callback=2

# Stop the application
ctrl-c

# Clean up containers and volumes
podman compose down --volumes
```

Using docker compose with Podman:
```bash
# The same Docker Compose commands work with Podman if you've set up the compatibility layer
docker compose up --build
docker compose up --build --scale worker-query=2 --scale worker-callback=2
```

Additional Podman-specific commands that might be helpful:
```bash
# List all containers
podman ps -a

# View container logs
podman logs <container_name>

# Remove all containers and pods
podman pod rm -f -a

# Clean up unused images and volumes
podman system prune --volumes
```

##### Further Information on transitioning from Docker to Podman:

NOTE: As of 3/29/24 we recommend using `Podman` and `Podman Desktop` instead of `Docker` and `Docker Desktop`. It will be our default development environment going forward.
There are many guides to transitioning from `Docker` (Desktop) to `Podman` (Desktop), but here's a rough outline of our "golden path."

1. Uninstall `Docker Desktop`. This will require a GUI uninstall and looking through your apps + filesystem for remnants.
2. Install `Podman` and `Podman Desktop`. You'll also explicitly have to provision a `Podman Machine` if you're on a Mac.
3. Enable the "Docker compatibility add-on" available in `Podman Desktop`. This will route traffic headed for a Docker machine to the running Podman machine. (Under the hood, this points Podman at the Docker socket."
4. Install `docker-compose`. This is a standalone, open source tool that `Podman Compose` delegates compose responsibilities to.

At this point, the `Podman` docs claim that one should have moved over to `Podman` as a drop-in replacement for `Docker`. However, here are two steps that we noticed were necessary in some cases.

1. In `$HOME/.docker/config.json` replace "credsStore" with "credStore" (minus an 's') to solve registry credentialing problems.
2. Set `export DOCKER_HOST=<your_podman_machine_socket_path>` to the `Podman machine`'s socket on your system, which you can find in the `Resources` tab of `Podman Desktop`. The path starts with `unix://`.


#### Option 2: Using Docker

If you choose to use Docker, you'll need:
1. Docker installed on your system: [Install Docker](https://docs.docker.com/engine/install)
2. Docker Compose installed: [Docker Compose](https://docs.docker.com/compose/install)

If the following commands return sensible results then Docker and Docker Compose are installed:
Verify your installation with:
```bash
docker && docker compose || docker-compose
```

**Optional, but recommended to Install Docker Desktop**

All of the build/tear-down is done with `docker compose`.

To start the application, run at the top-level of the 8Knot directory:

```bash
docker compose up --build
```

Due to a known deadlock, we recommend scaling-up the number of worker-pool pods deployed.
There need to be (#visualizations + 1) celery threads available for the callback_worker pool.

A concrete example: I have 6 CPU's allocated to my Docker runtime, so Celery workers will default to a concurrency of 6 processes.
However, there are 7 visualizations on the Overview page. Therefore, I will scale the 'callback_worker' pod to 2 instances,
guaranteeing that there are (2 \* #CPUs = 12) available processing celery threads, ensuring that the known deadlock will be avoided.

```bash
docker compose up --build --scale worker-query=2 --scale worker-callback=2
```

> **Out of Memory (OOM) issues:** If your local instance is running out of memory, try reducing the number of concurrent workers
> by lowering the `--concurrency` value in `docker-compose.yml` for the `worker-callback` and `worker-query` services.
> The default concurrency is 8; reducing it to 2 or 4 can significantly reduce memory usage at the cost of slower data loading.

To stop the application:

```bash
ctrl-c
```

To clean up the stopped containers, run:

```bash
docker compose down --volumes
```

### Build and Run

8Knot is a multi-container application.

The app-server, worker-pools, redis-broker, and postgres-cache containers communicate with one another via docker networking.

All of the build/tear-down is done with `docker compose`.

To start the application, run at the top-level of the 8Knot directory:

```bash
podman compose up --build
```

Due to a known deadlock, we recommend scaling-up the number of worker-pool pods deployed.
There need to be (#visualizations + 1) celery threads available for the callback_worker pool.

A concrete example: I have 6 CPU's allocated to my Docker runtime, so Celery workers will default to a concurrency of 6 processes.
However, there are 7 visualizations on the Overview page. Therefore, I will scale the 'callback_worker' pod to 2 instances,
guaranteeing that there are (2 \* #CPUs = 12) available processing celery threads, ensuring that the known deadlock will be avoided.

```bash
podman compose up --build --scale worker-query=2 --scale worker-callback=2
```

To stop the application:

```bash
ctrl-c
```

To clean up the stopped containers, run:

```bash
podman compose down --volumes
```

The application should be available locally at 'http://localhost:8080'

---

## Development Note

We use pre-commit to handle our code quality checks. Before you make a PR please make sure to install pre-commit and pass all of the checks that it requires.
