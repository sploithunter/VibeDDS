#include <dds/DCPS/Marked_Default_Qos.h>
#include <dds/DCPS/Service_Participant.h>
#include <dds/DCPS/StaticIncludes.h>

#include <ace/OS_NS_unistd.h>

#include "ShapeTypeTypeSupportImpl.h"

int main(int argc, char* argv[]) {
  try {
    DDS::DomainParticipantFactory_var dpf = TheParticipantFactoryWithArgs(argc, argv);
    DDS::DomainParticipant_var participant =
      dpf->create_participant(0, PARTICIPANT_QOS_DEFAULT, 0, 0);
    if (!participant) {
      return 1;
    }

    ShapeTypeTypeSupport_var ts = new ShapeTypeTypeSupportImpl();
    if (ts->register_type(participant, "") != DDS::RETCODE_OK) {
      return 2;
    }

    CORBA::String_var type_name = ts->get_type_name();
    DDS::Topic_var topic = participant->create_topic(
      "Square", type_name, TOPIC_QOS_DEFAULT, 0, 0);
    if (!topic) {
      return 3;
    }

    DDS::Publisher_var pub = participant->create_publisher(PUBLISHER_QOS_DEFAULT, 0, 0);
    if (!pub) {
      return 4;
    }

    DDS::DataWriterQos dw_qos;
    pub->get_default_datawriter_qos(dw_qos);
    dw_qos.reliability.kind = DDS::BEST_EFFORT_RELIABILITY_QOS;

    DDS::DataWriter_var writer = pub->create_datawriter(topic, dw_qos, 0, 0);
    ShapeTypeDataWriter_var shape_writer = ShapeTypeDataWriter::_narrow(writer);
    if (!shape_writer) {
      return 5;
    }

    DDS::PublicationMatchedStatus status;
    writer->get_publication_matched_status(status);
    std::cout << "OpenDDS matched subscriptions (initial): "
              << status.current_count << std::endl;

    ACE_OS::sleep(ACE_Time_Value(1, 0));
    writer->get_publication_matched_status(status);
    std::cout << "OpenDDS matched subscriptions (after 1s): "
              << status.current_count << std::endl;

    ShapeType sample;
    sample.color = "VIBE";
    sample.x = 10;
    sample.y = 10;
    sample.shapesize = 30;
    sample.fillKind = SOLID_FILL;
    sample.angle = 0;

    for (int i = 0; i < 200; ++i) {
      sample.x += 1;
      sample.y += 1;
      shape_writer->write(sample, DDS::HANDLE_NIL);
      ACE_OS::sleep(ACE_Time_Value(0, 200000));
    }

    participant->delete_contained_entities();
    dpf->delete_participant(participant);
    TheServiceParticipant->shutdown();
    return 0;
  } catch (const CORBA::Exception& ex) {
    ex._tao_print_exception("OpenDDS publisher");
    return 1;
  }
}
