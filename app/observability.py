# Importing necessary modules from OpenTelemetry, Prometheus, FastAPI, and logging libraries

from opentelemetry import trace  # Main entry point for tracing
from opentelemetry.exporter.jaeger.thrift import JaegerExporter  # Exporter for sending spans to Jaeger
from opentelemetry.sdk.resources import SERVICE_NAME, Resource  # Defines resources, such as service name
from opentelemetry.sdk.trace import TracerProvider  # Provides tracing capabilities
from opentelemetry.sdk.trace.export import BatchSpanProcessor  # Processes spans in batches for efficiency
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # Auto-instruments FastAPI for tracing
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # Auto-instruments SQLAlchemy
from prometheus_fastapi_instrumentator import Instrumentator  # Auto-instruments FastAPI for Prometheus metrics
from prometheus_client import make_asgi_app, Counter, Histogram, Gauge  # Prometheus client for custom metrics
import logging  # Standard logging library
from pythonjsonlogger import jsonlogger  # Formatter for structured JSON logs
from fastapi import Request, FastAPI  # FastAPI framework
from .database import engine  # Database engine for SQLAlchemy
import time  # For timing request durations
import os  # For environment variable access

# Define custom Prometheus metrics
# Counters, Gauges, and Histograms track different aspects of request handling

REQUEST_COUNT = Counter("http_requests_total", "Total number of HTTP requests")
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Duration of HTTP requests in seconds")
IN_PROGRESS = Gauge("in_progress_requests", "Number of HTTP requests in progress")


def setup_logging():
    """
    Sets up structured JSON logging for the application.
    Logs are formatted in JSON and can be sent to a central log management system like Loki.
    The log level can be dynamically set via an environment variable.
    """
    logger = logging.getLogger()
    logger.handlers.clear()  # Clear any existing handlers to avoid duplicate logs

    # Get the log level from an environment variable, default to INFO if not set
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Set up a stream handler that writes logs to stdout
    logHandler = logging.StreamHandler()
    
    # Use a JSON formatter to structure the logs
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s',
        timestamp=True  # Include timestamp in logs
    )
    
    # Apply the formatter to the log handler
    logHandler.setFormatter(formatter)
    logHandler.setLevel(getattr(logging, log_level, logging.INFO))  # Set handler level based on environment variable
    logger.addHandler(logHandler)  # Attach the handler to the logger

    # Set the log level for the logger
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    logger.propagate = False  # Prevent logs from being propagated to ancestor loggers


def setup_tracing():
    """
    Sets up OpenTelemetry tracing for the application.
    Configures Jaeger as the tracing backend, and sets the service name.
    Traces are batched and sent to the Jaeger agent for processing.
    """
    # Define the service name for trace attribution
    resource = Resource(attributes={
        SERVICE_NAME: "fastapi-app"
    })

    # Set up Jaeger as the trace exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",  # Jaeger agent hostname
        agent_port=6831,  # Jaeger agent port
    )

    # Create a TracerProvider with the defined resource
    provider = TracerProvider(resource=resource)

    # Use a BatchSpanProcessor to handle spans efficiently
    processor = BatchSpanProcessor(jaeger_exporter)
    provider.add_span_processor(processor)

    # Set the global tracer provider for use throughout the application
    trace.set_tracer_provider(provider)


def setup_metrics(app: FastAPI):
    """
    Sets up Prometheus metrics for the FastAPI application.
    Auto-instruments the FastAPI application and exposes a /metrics endpoint.
    """
    # Instrument FastAPI for Prometheus metrics collection
    Instrumentator().instrument(app).expose(app)
    
    # Create a separate ASGI app for exposing metrics
    metrics_app = make_asgi_app()
    
    # Mount the metrics app at the /metrics endpoint
    app.mount("/metrics", metrics_app)


def setup_logging_middleware(app: FastAPI):
    """
    Adds middleware to the FastAPI application for logging and metrics collection.
    Logs details about each HTTP request and updates custom Prometheus metrics.
    """
    logger = logging.getLogger()

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """
        Middleware that logs request details and updates Prometheus metrics.
        It logs the request method, URL, status code, client host, and duration.
        """
        start_time = time.time()  # Record the start time of the request
        IN_PROGRESS.inc()  # Increment the gauge for in-progress requests

        # Pass the request to the next middleware or route handler
        response = await call_next(request)

        # Calculate how long the request took to process
        duration = time.time() - start_time

        # Update Prometheus metrics
        REQUEST_COUNT.inc()  # Increment the total request count
        REQUEST_LATENCY.observe(duration)  # Record the request duration in the histogram
        IN_PROGRESS.dec()  # Decrement the in-progress request gauge

        # Log the details of the processed request
        logger.info(f"Request processed", extra={
            "method": request.method,
            "url": str(request.url),
            "status_code": response.status_code,
            "client_host": request.client.host,
            "duration": duration
        })
        return response


def setup_observability(app: FastAPI):
    """
    Orchestrates the setup of all observability components:
    - Logging: Structured JSON logging.
    - Tracing: OpenTelemetry tracing with Jaeger as the exporter.
    - Metrics: Prometheus metrics collection and exposure.
    - Middleware: HTTP request logging and metrics update middleware.
    """
    setup_logging()  # Set up structured logging
    setup_tracing()  # Set up tracing with Jaeger
    setup_metrics(app)  # Set up Prometheus metrics
    setup_logging_middleware(app)  # Add middleware for logging and metrics

    # Auto-instrument FastAPI routes and SQLAlchemy for tracing
    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument(engine=engine)
