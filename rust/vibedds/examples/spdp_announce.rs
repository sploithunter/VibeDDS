/// SPDP announce example - sends periodic participant announcements.
///
/// Run with: cargo run --example spdp_announce
///
/// Use Python spdp_listen.py to verify interop:
///   python examples/spdp_listen.py

use std::time::Duration;
use vibedds::participant::DomainParticipant;

fn main() {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();

    let mut participant = DomainParticipant::new(0, 0);

    participant.on_participant_discovered(|p| {
        log::info!(
            "Discovered participant: {:?}, vendor={:?}",
            p.guid_prefix,
            p.vendor_id
        );
    });

    participant.on_participant_lost(|p| {
        log::info!("Lost participant: {:?}", p.guid_prefix);
    });

    log::info!("Starting SPDP announcer on domain 0...");
    log::info!("GUID prefix: {:?}", participant.guid_prefix());

    if let Err(e) = participant.start() {
        log::error!("Failed to start participant: {}", e);
        return;
    }

    // Set faster announce interval for testing
    participant.set_spdp_announce_interval(Duration::from_secs(5));

    log::info!("Running for 60 seconds. Use Python spdp_listen.py to see announcements.");

    if let Err(e) = participant.spin(Some(Duration::from_secs(60))) {
        log::error!("Error in spin loop: {}", e);
    }

    participant.stop();
    log::info!("Done.");
}
