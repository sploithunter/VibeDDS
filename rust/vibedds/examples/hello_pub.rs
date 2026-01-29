/// HelloWorld publisher example - publishes HelloWorld messages
/// that can be received by rtiddsspy or hello_sub.
///
/// Run: cargo run --example hello_pub
/// Then in another terminal: rtiddsspy -domainId 0 -printSample
/// Or: cargo run --example hello_sub

use std::time::Duration;

use vibedds::participant::DomainParticipant;
use vibedds::qos::QosPolicy;
use vibedds::type_support::HelloWorldType;

fn main() {
    // Initialize logging
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .init();

    println!("VibeDDS HelloWorld Publisher");
    println!("=============================");
    println!("Publishing HelloWorld messages.");
    println!("Run rtiddsspy -printSample to see the data.");
    println!();

    // Create participant
    let mut participant = DomainParticipant::new(0, 0);
    participant.set_spdp_announce_interval(Duration::from_secs(5));

    // Start the participant
    participant.start().expect("Failed to start participant");
    println!("Participant started: {:?}", participant.guid_prefix());

    // Send initial SPDP announcement
    participant.announce_spdp().expect("Failed to announce SPDP");

    // Create a HelloWorld DataWriter
    let writer_qos = QosPolicy::reliable();
    let writer_arc = participant.create_writer(
        "HelloWorld",
        "HelloWorld",
        writer_qos,
    );
    println!("Created HelloWorld writer");

    // Set up discovery callback
    participant.on_participant_discovered(|p| {
        println!(
            "Discovered participant: {:?}, vendor={:?}",
            p.guid_prefix, p.vendor_id
        );
    });

    println!();
    println!("Publishing every 2 seconds... Press Ctrl+C to stop.");
    println!();

    let mut count = 0u32;
    let mut last_publish = std::time::Instant::now();

    // Run the event loop
    loop {
        if let Err(e) = participant.spin_once(Duration::from_millis(100)) {
            log::error!("Error in spin: {}", e);
        }

        // Periodically announce SEDP
        if let Err(e) = participant.announce_sedp() {
            log::error!("Error in SEDP announce: {}", e);
        }

        // Publish every 2 seconds
        if last_publish.elapsed() >= Duration::from_secs(2) {
            count += 1;
            let message = format!("Hello DDS World #{}", count);
            let payload = HelloWorldType::serialize(&message);

            {
                let mut writer = writer_arc.lock().unwrap();
                if let Err(e) = participant.send_data(&mut writer, &payload) {
                    log::error!("Failed to send data: {}", e);
                } else {
                    println!("Published: {}", message);
                }
            }

            last_publish = std::time::Instant::now();
        }

        std::thread::sleep(Duration::from_millis(50));
    }
}
