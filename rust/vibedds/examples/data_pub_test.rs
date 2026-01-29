/// Test publisher - publishes a few HelloWorld messages then exits.
/// Used by integration tests.
///
/// Run: cargo run --example data_pub_test

use std::time::Duration;

use vibedds::participant::DomainParticipant;
use vibedds::qos::QosPolicy;
use vibedds::type_support::HelloWorldType;

fn main() {
    // Initialize logging
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .init();

    println!("VibeDDS Test Publisher");

    // Create participant
    let mut participant = DomainParticipant::new(0, 0);
    participant.set_spdp_announce_interval(Duration::from_secs(2));

    // Start the participant
    participant.start().expect("Failed to start participant");
    println!("Participant started: {:?}", participant.guid_prefix());

    // Send initial SPDP announcement
    participant.announce_spdp().expect("Failed to announce SPDP");

    // Create a HelloWorld DataWriter
    let writer_qos = QosPolicy::best_effort();  // Best-effort for simpler testing
    let writer_arc = participant.create_writer(
        "HelloWorld",
        "HelloWorld",
        writer_qos,
    );
    println!("Created HelloWorld writer");

    // Wait for discovery
    println!("Waiting for discovery...");
    for _ in 0..20 {
        if let Err(e) = participant.spin_once(Duration::from_millis(100)) {
            log::error!("Error in spin: {}", e);
        }
        if let Err(e) = participant.announce_sedp() {
            log::error!("Error in SEDP announce: {}", e);
        }
    }

    // Publish 5 messages
    println!("Publishing 5 messages...");
    for i in 1..=5 {
        let message = format!("Hello from Rust #{}", i);
        let payload = HelloWorldType::serialize(&message);

        {
            let mut writer = writer_arc.lock().unwrap();
            if let Err(e) = participant.send_data(&mut writer, &payload) {
                log::error!("Failed to send data: {}", e);
            } else {
                println!("Published: {}", message);
            }
        }

        // Spin to process any incoming traffic
        for _ in 0..5 {
            let _ = participant.spin_once(Duration::from_millis(50));
        }
    }

    // Final spin to let messages propagate
    println!("Waiting for delivery...");
    for _ in 0..10 {
        let _ = participant.spin_once(Duration::from_millis(100));
    }

    participant.stop();
    println!("Test publisher finished");
}
