"""Trace context and low-cardinality backend metrics; optional OTLP export."""
import json
import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
import functools
import inspect
import asyncio
from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from shared.utils.turns import job_claim

_configured = False
class RotatingOutput:
    def __init__(self,path):
        self.handler=RotatingFileHandler(path,maxBytes=10*1024*1024,backupCount=3,encoding='utf-8')
    def write(self,text):
        self.handler.handle(logging.LogRecord('roleplay.telemetry',logging.INFO,'',0,text.rstrip(),(),None))
    def flush(self):
        self.handler.flush()

def setup_telemetry(service):
    global _configured
    if _configured:
        return
    provider = TracerProvider(resource=Resource.create({'service.name':service}))
    directory=Path('logs/telemetry')
    directory.mkdir(parents=True,exist_ok=True)
    path = os.getenv('TRACE_FILE',str(directory/f'{service}-{os.getpid()}.traces.log'))
    if path:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(out=RotatingOutput(path))))
    endpoint = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT')
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip('/')+'/v1/traces')))
    trace.set_tracer_provider(provider)
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader,ConsoleMetricExporter
    metric_file=RotatingOutput(directory/f'{service}-{os.getpid()}.metrics.log')
    metrics.set_meter_provider(MeterProvider(resource=Resource.create({'service.name':service}),metric_readers=[PeriodicExportingMetricReader(ConsoleMetricExporter(out=metric_file),export_interval_millis=10000)]))
    _configured = True

def tracer():
    return trace.get_tracer('roleplay.backend')

async def flush_telemetry():
    """Make local exports timely, including idle low-traffic processes."""
    while True:
        await asyncio.sleep(5)
        provider=trace.get_tracer_provider()
        if hasattr(provider,'force_flush'):
            await asyncio.to_thread(provider.force_flush,3000)
        provider=metrics.get_meter_provider()
        if hasattr(provider,'force_flush'):
            await asyncio.to_thread(provider.force_flush,3000)

def traced(name):
    def decorate(function):
        if inspect.isasyncgenfunction(function):
            @functools.wraps(function)
            async def stream(*args,**kwargs):
                with tracer().start_as_current_span(name):
                    async for item in function(*args,**kwargs):
                        yield item
            return stream
        @functools.wraps(function)
        async def call(*args,**kwargs):
            with tracer().start_as_current_span(name):
                return await function(*args,**kwargs)
        return call
    return decorate

def correlation():
    claim = job_claim.get()
    span = trace.get_current_span().get_span_context()
    return {'turn_id':claim.turn_id if claim else None,'job_id':claim.id if claim else None,
            'stage':claim.stage if claim else None,'fence':claim.fence if claim else None,
            'trace_id':format(span.trace_id,'032x') if span.is_valid else None}
