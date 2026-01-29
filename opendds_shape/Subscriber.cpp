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

    DDS::Subscriber_var sub = participant->create_subscriber(SUBSCRIBER_QOS_DEFAULT, 0, 0);
    if (!sub) {
      return 4;
    }

    DDS::DataReaderQos dr_qos;
    sub->get_default_datareader_qos(dr_qos);
    dr_qos.reliability.kind = DDS::BEST_EFFORT_RELIABILITY_QOS;

    DDS::DataReader_var reader = sub->create_datareader(topic, dr_qos, 0, 0);
    ShapeTypeDataReader_var shape_reader = ShapeTypeDataReader::_narrow(reader);
    if (!shape_reader) {
      return 5;
    }

    for (int i = 0; i < 200; ++i) {
      ShapeTypeSeq data;
      DDS::SampleInfoSeq info;
      DDS::ReturnCode_t rc = shape_reader->take(
        data, info, DDS::LENGTH_UNLIMITED,
        DDS::ANY_SAMPLE_STATE, DDS::ANY_VIEW_STATE, DDS::ANY_INSTANCE_STATE);
      if (rc == DDS::RETCODE_OK) {
        for (CORBA::ULong j = 0; j < data.length(); ++j) {
          if (info[j].valid_data) {
            const ShapeType& s = data[j];
            std::cout << "OPEN DDS RECEIVED: color=" << s.color.in()
                      << " x=" << s.x << " y=" << s.y
                      << " size=" << s.shapesize
                      << " fillKind=" << s.fillKind
                      << " angle=" << s.angle << std::endl;
          }
        }
        shape_reader->return_loan(data, info);
      }
      ACE_OS::sleep(ACE_Time_Value(0, 200000));
    }

    participant->delete_contained_entities();
    dpf->delete_participant(participant);
    TheServiceParticipant->shutdown();
    return 0;
  } catch (const CORBA::Exception& ex) {
    ex._tao_print_exception("OpenDDS subscriber");
    return 1;
  }
}
