import json
import logging
import threading
from queue import Queue
from confluent_kafka import Producer, Consumer, KafkaError

try:
    from config import get_config
    CFG = get_config()
except ImportError:
    class FallbackConfig:
        KAFKA_BROKER = "localhost:19092"
    CFG = FallbackConfig()

logger = logging.getLogger(__name__)

# Fallback in-memory bus if Redpanda isn't running
_MOCK_BUS = {
    "clinical_telemetry": Queue(),
    "agent_actions": Queue()
}
_USE_MOCK = False


def _check_kafka():
    global _USE_MOCK
    try:
        # Quick test connection
        p = Producer({'bootstrap.servers': CFG.KAFKA_BROKER, 'message.timeout.ms': 1000})
        p.produce('test_topic', b'test')
        p.flush(timeout=1.0)
    except Exception:
        logger.warning(f"Could not connect to Redpanda at {CFG.KAFKA_BROKER}. Using Mock Bus.")
        _USE_MOCK = True

# Initialize check
_check_kafka()


class TelemetryProducer:
    def __init__(self, topic="clinical_telemetry"):
        self.topic = topic
        if not _USE_MOCK:
            self.producer = Producer({
                'bootstrap.servers': CFG.KAFKA_BROKER,
                'client.id': 'clinical-ui-producer',
                'acks': '0' # Fire and forget for low latency telemetry
            })
            
    def publish(self, event_type: str, payload: dict):
        message = {
            "type": event_type,
            "data": payload
        }
        
        if _USE_MOCK:
            _MOCK_BUS[self.topic].put(message)
            return
            
        try:
            self.producer.produce(
                self.topic, 
                key=event_type.encode('utf-8'),
                value=json.dumps(message).encode('utf-8')
            )
            self.producer.poll(0)
        except Exception as e:
            logger.error(f"Kafka publish error: {e}")

    def flush(self):
        if not _USE_MOCK:
            self.producer.flush()


class TelemetryConsumer:
    def __init__(self, topic="clinical_telemetry", group_id="agent_processor"):
        self.topic = topic
        self._running = False
        
        if not _USE_MOCK:
            self.consumer = Consumer({
                'bootstrap.servers': CFG.KAFKA_BROKER,
                'group.id': group_id,
                'auto.offset.reset': 'latest'
            })
            self.consumer.subscribe([self.topic])

    def start_listening(self, callback):
        self._running = True
        self.thread = threading.Thread(target=self._consume_loop, args=(callback,), daemon=True)
        self.thread.start()

    def _consume_loop(self, callback):
        while self._running:
            if _USE_MOCK:
                try:
                    msg = _MOCK_BUS[self.topic].get(timeout=0.5)
                    callback(msg)
                except Exception:
                    pass
                continue

            msg = self.consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    logger.error(f"Kafka consumer error: {msg.error()}")
                continue
            
            try:
                data = json.loads(msg.value().decode('utf-8'))
                callback(data)
            except Exception as e:
                logger.error(f"Error parsing kafka message: {e}")

    def stop(self):
        self._running = False
        if not _USE_MOCK:
            self.consumer.close()
