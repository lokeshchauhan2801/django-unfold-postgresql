from .interfaces import ProcessingBackend, ProcessingRequest


class KafkaProcessingBackend(ProcessingBackend):
    TOPIC = 'document.processing.requested'

    def dispatch(self, request: ProcessingRequest) -> str:
        import uuid
        from infrastructure.kafka.producer import KafkaEventPublisher
        from infrastructure.kafka.interfaces import DomainEvent
        event = DomainEvent(
            event_type='document.processing.requested',
            company_id=request.company_id,
            user_id=request.user_id,
            resource_id=request.document_id,
            payload={'backend': request.backend},
        )
        publisher = KafkaEventPublisher()
        publisher.publish(self.TOPIC, event)
        return event.event_id

    def get_status(self, job_id: str) -> str:
        return 'PUBLISHED'  # Kafka is fire-and-forget from dispatcher perspective
