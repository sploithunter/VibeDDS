/*
 * Minimal RTI C publisher for interop testing with VibeDDS.
 * Uses RTI's builtin String type (no IDL generation).
 *
 * Build:
 *   make
 *
 * Run:
 *   ./simple_pub
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "ndds/ndds_c.h"

int main(int argc, char *argv[]) {
    DDS_DomainParticipant *participant = NULL;
    DDS_Publisher *publisher = NULL;
    DDS_Topic *topic = NULL;
    DDS_DataWriter *writer = NULL;
    DDS_StringDataWriter *string_writer = NULL;
    DDS_ReturnCode_t retcode;
    int domain_id = 0;
    int count = 0;
    int max_count = 100;
    char message[256];

    printf("RTI Simple String Publisher starting on domain %d...\n", domain_id);

    /* Create participant */
    participant = DDS_DomainParticipantFactory_create_participant(
        DDS_TheParticipantFactory, domain_id,
        &DDS_PARTICIPANT_QOS_DEFAULT,
        NULL, DDS_STATUS_MASK_NONE);

    if (participant == NULL) {
        printf("Failed to create participant\n");
        return -1;
    }
    printf("Participant created\n");

    /* Register builtin String type */
    const char *type_name = DDS_StringTypeSupport_get_type_name();
    retcode = DDS_StringTypeSupport_register_type(participant, type_name);
    if (retcode != DDS_RETCODE_OK) {
        printf("Failed to register String type: %d\n", retcode);
        return -1;
    }
    printf("Type '%s' registered\n", type_name);

    /* Create topic "TestTopic" */
    topic = DDS_DomainParticipant_create_topic(
        participant, "TestTopic", type_name,
        &DDS_TOPIC_QOS_DEFAULT, NULL, DDS_STATUS_MASK_NONE);
    if (topic == NULL) {
        printf("Failed to create topic\n");
        return -1;
    }
    printf("Topic 'TestTopic' created\n");

    /* Create publisher */
    publisher = DDS_DomainParticipant_create_publisher(
        participant, &DDS_PUBLISHER_QOS_DEFAULT,
        NULL, DDS_STATUS_MASK_NONE);
    if (publisher == NULL) {
        printf("Failed to create publisher\n");
        return -1;
    }

    /* Create writer with BEST_EFFORT reliability */
    struct DDS_DataWriterQos writer_qos = DDS_DataWriterQos_INITIALIZER;
    DDS_Publisher_get_default_datawriter_qos(publisher, &writer_qos);
    writer_qos.reliability.kind = DDS_BEST_EFFORT_RELIABILITY_QOS;

    writer = DDS_Publisher_create_datawriter(
        publisher, topic, &writer_qos,
        NULL, DDS_STATUS_MASK_NONE);
    if (writer == NULL) {
        printf("Failed to create writer\n");
        return -1;
    }
    string_writer = DDS_StringDataWriter_narrow(writer);
    printf("DataWriter created (BEST_EFFORT)\n");

    /* Wait for discovery */
    printf("Waiting 2 seconds for discovery...\n");
    sleep(2);

    /* Check matched subscriptions */
    struct DDS_PublicationMatchedStatus status;
    DDS_DataWriter_get_publication_matched_status(writer, &status);
    printf("Matched subscriptions: %d\n", status.current_count);

    /* Publish samples */
    printf("Publishing samples...\n");

    while (count < max_count) {
        snprintf(message, sizeof(message), "Hello from RTI! count=%d", count);

        /* Write */
        retcode = DDS_StringDataWriter_write(string_writer, message, &DDS_HANDLE_NIL);
        if (retcode != DDS_RETCODE_OK) {
            printf("Write failed: %d\n", retcode);
        } else {
            printf("[%d] Wrote: %s\n", count, message);
        }

        count++;
        usleep(500000); /* 500ms */

        /* Check matched subscriptions periodically */
        if (count % 5 == 0) {
            DDS_DataWriter_get_publication_matched_status(writer, &status);
            printf("  Matched subscriptions: %d\n", status.current_count);
        }
    }

    printf("Done. Cleaning up...\n");

    /* Cleanup */
    DDS_DomainParticipant_delete_contained_entities(participant);
    DDS_DomainParticipantFactory_delete_participant(DDS_TheParticipantFactory, participant);

    return 0;
}
