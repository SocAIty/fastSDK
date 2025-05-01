# FastSDK - Software Architecture

FastSDK is a modular, event-driven, **async-first job and service management framework**, designed for orchestrating API-based workflows in a resilient and stateful manner using the **SAGA pattern**.

---

## 🧱 Overview

FastSDK consists of three core domains:

1. **Job Management** – Lifecycle coordination for complex jobs across phases.
2. **Service Interaction** – Abstracted, programmable clients for communicating with OpenAPI services.
3. **Service Management** – Definition, parsing, and client generation for services.

---

## 🧩 Components

### 🚦 Job Management (SAGA-based)

| Component         | Description |
|------------------|-------------|
| `JobOrchestrator` | Manages the lifecycle of jobs using the SAGA pattern. Handles phase transitions, calls async job execution, and monitors state. |
| `JobStore`        | A centralized registry of all jobs, tracking them across phases. |
| `Job`      | Represents a single job with all relevant state, service and endpoint definitions, request data, and results. |
| `AsyncJobManager` | Runs an asyncio event loop in a separate thread, responsible for managing async execution. |
| `AsyncJob`        | Wraps coroutines or futures into manageable objects with lifecycle callbacks and state handling. |
| `ProgressBar`     | Singleton wrapper around `tqdm` for visualizing progress across job stages. |

---

### 🔌 Service Interaction

| Component       | Description |
|----------------|-------------|
| `APIClient`     | Communicates with a specific service using its service definition. Can be subclassed to customize behavior. Handles sending requests, polling, and uploading files. |
| `RequestBuilder`| Stateless utility for building the payload for `httpx` requests of the API Client. Integrates with `fast-cloud` for file uploads. |

---

### 📚 Service Management

| Component         | Description |
|------------------|-------------|
| `ServiceDefinition` | A Pydantic model representing an OpenAPI-based service and its endpoints. |
| `ServiceManager`    | Loads, organizes, and manages all available service definitions. |
| `OpenAPIParser`     | Parses an OpenAPI spec (JSON) into a structured `ServiceDefinition`. |
| `ClientGenerator`   | Dynamically generates specialized `APIClient` classes from service definitions. |

---

