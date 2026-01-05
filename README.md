# Michot Marefiya Backend

The backend for the Michot Marefiya hospitality platform. Built with Django and Django REST Framework, this service handles property listings, complex booking logic, secure payments, and background inventory management.

---

## 🚀 Tech Stack

*   **Runtime**: Python 3.12+
*   **Framework**: [Django 5.2.5+](https://www.djangoproject.com/)
*   **API Layer**: [Django REST Framework 3.16+](https://www.django-rest-framework.org/)
*   **Database**: [PostgreSQL](https://www.postgresql.org/)
*   **Cache & Queue**: [Redis](https://redis.io/)
*   **Background Tasks**: [Celery](https://docs.celeryq.dev/) (Worker & Beat)
*   **Authentication**: SimpleJWT (OAuth2 compatible)
*   **Documentation**: [DRF Spectacular](https://github.com/tfranzel/drf-spectacular) (Swagger/OpenAPI 3.0)

---

## 🛠️ Getting Started (Local Development)

The easiest way to run the project is using **Docker**.

### Prerequisites
*   [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running.
*   A `.env` file in the root directory (based on `.env.example`).

### 1. Launch Services
```bash
docker compose up --build
```
This will start:
- **api**: The Django backend (Port 8000)
- **db**: PostgreSQL database
- **redis**: Message broker for Celery
- **celery**: Background task runner
- **celery-beat**: Periodic task scheduler (for inventory release/cleanup)
- **pgadmin**: Database management UI (Port 8001)

### 2. Run Migrations
```bash
docker compose exec api python manage.py migrate
```

### 3. Create Superuser
```bash
docker compose exec api python manage.py createsuperuser
```

---

## 🧪 Testing & Quality

We use `pytest` for our test suite.

### Run all tests
```bash
docker compose exec api pytest
```

### Run with coverage
```bash
docker compose exec api pytest --cov=apps
```

---

## 📂 Project Structure

```text
michot_marefiya_backend/
├── apps/               # Business logic segmented by domain
│   ├── account/        # User management & Profiles
│   ├── listing/        # Hotels, Rooms, Spaces, & Service Logic
│   ├── payment/        # Chapa Integration & Transactions
│   ├── core/           # Utilities and Shared models
│   └── favorites/      # User-saved properties
├── config/             # Django project configuration (Settings, URLs, WSGI)
├── docker/             # Dockerfiles for Dev and Prod
└── requirements/       # Pip dependency files
```

---

## 🛡️ API Documentation
Once the server is running, you can access the interactive documentation at:
- **Swagger UI**: `http://localhost:8000/api/docs/`
- **Redoc**: `http://localhost:8000/api/schema/redoc/`

---

## 🤝 Contributing
Please use the provided **GitHub Issue Templates** for Bug Reports and Feature Requests. Ensure all code adheres to the configured `ruff` linting rules before pushing. 