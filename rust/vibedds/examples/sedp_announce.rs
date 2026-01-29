/// SEDP announce example - registers a HelloWorld writer
/// that should be visible in rtiddsspy.
///
/// Run: cargo run --example sedp_announce
/// Then in another terminal: rtiddsspy -domainId 0

use std::time::Duration;

use vibedds::participant::DomainParticipant;
use vibedds::qos::QosPolicy;

fn main() {
    // Initialize logging
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .init();

    println!("VibeDDS SEDP Announce Example");
    println!("==============================");
    println!("This will register a HelloWorld DataWriter.");
    println!("Run rtiddsspy to see the endpoint.");
    println!();

    // Create participant
    let mut participant = DomainParticipant::new(0, 0);
    participant.set_spdp_announce_interval(Duration::from_secs(3));

    // Start the participant
    participant.start().expect("Failed to start participant");
    println!("Participant started: {:?}", participant.guid_prefix());

    // Send initial SPDP announcement
    participant.announce_spdp().expect("Failed to announce SPDP");

    // Register a HelloWorld DataWriter
    let writer_qos = QosPolicy::reliable();
    let writer_guid = participant.register_writer(
        "HelloWorld",
        "HelloWorld::HelloWorld",
        writer_qos,
    );
    println!("Registered HelloWorld writer: {:?}", writer_guid);

    // Also register a reader to demonstrate both
    let reader_qos = QosPolicy::best_effort();
    let reader_guid = participant.register_reader(
        "Square",
        "ShapeType",
        reader_qos,
    );
    println!("Registered Square reader: {:?}", reader_guid);

    // Set up discovery callback
    participant.on_participant_discovered(|p| {
        println!(
            "Discovered participant: {:?}, vendor={:?}",
            p.guid_prefix, p.vendor_id
        );
    });

    println!();
    println!("Running... Press Ctrl+C to stop.");
    println!();

    // Run the event loop
    loop {
        if let Err(e) = participant.spin_once(Duration::from_millis(100)) {
            log::error!("Error in spin: {}", e);
        }

        // Periodically re-announce SEDP
        if let Err(e) = participant.announce_sedp() {
            log::error!("Error in SEDP announce: {}", e);
        }

        std::thread::sleep(Duration::from_millis(100));
    }
}
