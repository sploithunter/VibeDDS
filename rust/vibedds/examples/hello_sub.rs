/// HelloWorld subscriber example - receives HelloWorld messages
/// from hello_pub or rtiddsspy.
///
/// Run: cargo run --example hello_sub
/// Then in another terminal: cargo run --example hello_pub

use std::time::Duration;

use vibedds::participant::DomainParticipant;
use vibedds::qos::QosPolicy;
use vibedds::type_support::HelloWorldType;

fn main() {
    // Initialize logging
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .init();

    println!("VibeDDS HelloWorld Subscriber");
    println!("==============================");
    println!("Waiting for HelloWorld messages...");
    println!("Run 'cargo run --example hello_pub' to publish.");
    println!();

    // Create participant
    let mut participant = DomainParticipant::new(0, 1); // participant_id=1 to avoid port conflicts
    participant.set_spdp_announce_interval(Duration::from_secs(5));

    // Start the participant
    participant.start().expect("Failed to start participant");
    println!("Participant started: {:?}", participant.guid_prefix());

    // Send initial SPDP announcement
    participant.announce_spdp().expect("Failed to announce SPDP");

    // Create a HelloWorld DataReader
    let reader_qos = QosPolicy::reliable();
    let reader_arc = participant.create_reader(
        "HelloWorld",
        "HelloWorld",
        reader_qos,
    );
    println!("Created HelloWorld reader");

    // Set up data callback
    {
        let mut reader = reader_arc.lock().unwrap();
        reader.on_data(|payload| {
            match HelloWorldType::deserialize(payload) {
                Ok(message) => println!("Received: {}", message),
                Err(e) => log::error!("Failed to deserialize: {}", e),
            }
        });
    }

    // Set up discovery callback
    participant.on_participant_discovered(|p| {
        println!(
            "Discovered participant: {:?}, vendor={:?}",
            p.guid_prefix, p.vendor_id
        );
    });

    println!();
    println!("Waiting for data... Press Ctrl+C to stop.");
    println!();

    // Run the event loop
    loop {
        if let Err(e) = participant.spin_once(Duration::from_millis(100)) {
            log::error!("Error in spin: {}", e);
        }

        // Periodically announce SEDP
        if let Err(e) = participant.announce_sedp() {
            log::error!("Error in SEDP announce: {}", e);
        }

        // Also check the buffer for any samples not delivered via callback
        {
            let mut reader = reader_arc.lock().unwrap();
            while let Some(sample) = reader.take_one() {
                match HelloWorldType::deserialize(&sample.data) {
                    Ok(message) => {
                        println!(
                            "[buffer] Received: {} (from {:?}, sn={})",
                            message,
                            sample.writer_guid.prefix,
                            sample.sequence_number.value()
                        );
                    }
                    Err(e) => log::error!("Failed to deserialize: {}", e),
                }
            }
        }

        std::thread::sleep(Duration::from_millis(50));
    }
}
