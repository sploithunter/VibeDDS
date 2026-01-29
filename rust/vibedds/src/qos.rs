/// QoS policies and RxO (Requested/Offered) compatibility matching.

use crate::types::Duration;

/// Reliability QoS kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[repr(u32)]
pub enum ReliabilityKind {
    BestEffort = 1,
    Reliable = 2,
}

impl ReliabilityKind {
    pub fn from_u32(v: u32) -> Option<Self> {
        match v {
            1 => Some(Self::BestEffort),
            2 => Some(Self::Reliable),
            _ => None,
        }
    }
}

/// Durability QoS kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[repr(u32)]
pub enum DurabilityKind {
    Volatile = 0,
    TransientLocal = 1,
    Transient = 2,
    Persistent = 3,
}

impl DurabilityKind {
    pub fn from_u32(v: u32) -> Option<Self> {
        match v {
            0 => Some(Self::Volatile),
            1 => Some(Self::TransientLocal),
            2 => Some(Self::Transient),
            3 => Some(Self::Persistent),
            _ => None,
        }
    }
}

/// Ownership QoS kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u32)]
pub enum OwnershipKind {
    Shared = 0,
    Exclusive = 1,
}

impl OwnershipKind {
    pub fn from_u32(v: u32) -> Option<Self> {
        match v {
            0 => Some(Self::Shared),
            1 => Some(Self::Exclusive),
            _ => None,
        }
    }
}

/// Liveliness QoS kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[repr(u32)]
pub enum LivelinessKind {
    Automatic = 0,
    ManualByParticipant = 1,
    ManualByTopic = 2,
}

impl LivelinessKind {
    pub fn from_u32(v: u32) -> Option<Self> {
        match v {
            0 => Some(Self::Automatic),
            1 => Some(Self::ManualByParticipant),
            2 => Some(Self::ManualByTopic),
            _ => None,
        }
    }
}

/// Destination order QoS kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
#[repr(u32)]
pub enum DestinationOrderKind {
    ByReceptionTimestamp = 0,
    BySourceTimestamp = 1,
}

impl DestinationOrderKind {
    pub fn from_u32(v: u32) -> Option<Self> {
        match v {
            0 => Some(Self::ByReceptionTimestamp),
            1 => Some(Self::BySourceTimestamp),
            _ => None,
        }
    }
}

/// History QoS kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u32)]
pub enum HistoryKind {
    KeepLast = 0,
    KeepAll = 1,
}

impl HistoryKind {
    pub fn from_u32(v: u32) -> Option<Self> {
        match v {
            0 => Some(Self::KeepLast),
            1 => Some(Self::KeepAll),
            _ => None,
        }
    }
}

/// Aggregated QoS settings for an endpoint.
#[derive(Debug, Clone)]
pub struct QosPolicy {
    pub reliability: ReliabilityKind,
    pub reliability_max_blocking_time: Duration,
    pub durability: DurabilityKind,
    pub ownership: OwnershipKind,
    pub liveliness: LivelinessKind,
    pub liveliness_lease_duration: Duration,
    pub deadline_period: Duration,
    pub destination_order: DestinationOrderKind,
    pub history: HistoryKind,
    pub history_depth: i32,
    pub partition: Option<Vec<String>>,
}

impl Default for QosPolicy {
    fn default() -> Self {
        Self {
            reliability: ReliabilityKind::BestEffort,
            reliability_max_blocking_time: Duration::ZERO,
            durability: DurabilityKind::Volatile,
            ownership: OwnershipKind::Shared,
            liveliness: LivelinessKind::Automatic,
            liveliness_lease_duration: Duration::INFINITE,
            deadline_period: Duration::INFINITE,
            destination_order: DestinationOrderKind::ByReceptionTimestamp,
            history: HistoryKind::KeepLast,
            history_depth: 1,
            partition: None,
        }
    }
}

impl QosPolicy {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn reliable() -> Self {
        Self {
            reliability: ReliabilityKind::Reliable,
            ..Self::default()
        }
    }

    pub fn best_effort() -> Self {
        Self::default()
    }

    /// QoS for builtin endpoints (SEDP).
    pub fn builtin_endpoint() -> Self {
        Self {
            reliability: ReliabilityKind::Reliable,
            durability: DurabilityKind::TransientLocal,
            history: HistoryKind::KeepLast,
            history_depth: 1,
            ..Self::default()
        }
    }
}

/// Check if offered QoS is compatible with requested QoS (RxO rules).
///
/// Returns true if the writer's offered QoS satisfies the reader's requested QoS.
pub fn qos_compatible(offered: &QosPolicy, requested: &QosPolicy) -> bool {
    // Reliability: offered must be >= requested
    if offered.reliability < requested.reliability {
        return false;
    }

    // Durability: offered must be >= requested
    if offered.durability < requested.durability {
        return false;
    }

    // Ownership: must match exactly
    if offered.ownership != requested.ownership {
        return false;
    }

    // Liveliness: offered must be >= requested (stricter is higher)
    if offered.liveliness < requested.liveliness {
        return false;
    }

    // Destination order: offered must be >= requested
    if offered.destination_order < requested.destination_order {
        return false;
    }

    // Partition: if both specify partitions, they must have at least one in common
    if let (Some(off_parts), Some(req_parts)) = (&offered.partition, &requested.partition) {
        let has_common = off_parts.iter().any(|p| req_parts.contains(p));
        if !has_common {
            return false;
        }
    }

    true
}

/// Serialize reliability QoS for SEDP parameter list.
/// Returns kind(u32) + max_blocking_time(Duration: i32+u32) = 12 bytes
pub fn serialize_reliability_qos(qos: &QosPolicy) -> [u8; 12] {
    let mut buf = [0u8; 12];
    buf[0..4].copy_from_slice(&(qos.reliability as u32).to_le_bytes());
    buf[4..8].copy_from_slice(&qos.reliability_max_blocking_time.seconds.to_le_bytes());
    buf[8..12].copy_from_slice(&qos.reliability_max_blocking_time.fraction.to_le_bytes());
    buf
}

/// Deserialize reliability QoS from parameter value.
pub fn deserialize_reliability_qos(data: &[u8]) -> Option<(ReliabilityKind, Duration)> {
    if data.len() < 12 {
        return None;
    }
    let kind = u32::from_le_bytes([data[0], data[1], data[2], data[3]]);
    let seconds = i32::from_le_bytes([data[4], data[5], data[6], data[7]]);
    let fraction = u32::from_le_bytes([data[8], data[9], data[10], data[11]]);

    Some((ReliabilityKind::from_u32(kind)?, Duration { seconds, fraction }))
}

/// Serialize durability QoS for SEDP parameter list.
pub fn serialize_durability_qos(qos: &QosPolicy) -> [u8; 4] {
    (qos.durability as u32).to_le_bytes()
}

/// Deserialize durability QoS from parameter value.
pub fn deserialize_durability_qos(data: &[u8]) -> Option<DurabilityKind> {
    if data.len() < 4 {
        return None;
    }
    let kind = u32::from_le_bytes([data[0], data[1], data[2], data[3]]);
    DurabilityKind::from_u32(kind)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_reliability_ordering() {
        assert!(ReliabilityKind::Reliable > ReliabilityKind::BestEffort);
    }

    #[test]
    fn test_durability_ordering() {
        assert!(DurabilityKind::Persistent > DurabilityKind::TransientLocal);
        assert!(DurabilityKind::TransientLocal > DurabilityKind::Volatile);
    }

    #[test]
    fn test_qos_compatible_same() {
        let qos = QosPolicy::default();
        assert!(qos_compatible(&qos, &qos));
    }

    #[test]
    fn test_qos_compatible_reliable_to_best_effort() {
        let offered = QosPolicy::reliable();
        let requested = QosPolicy::best_effort();
        assert!(qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_qos_incompatible_best_effort_to_reliable() {
        let offered = QosPolicy::best_effort();
        let requested = QosPolicy::reliable();
        assert!(!qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_qos_compatible_durability() {
        let mut offered = QosPolicy::default();
        offered.durability = DurabilityKind::TransientLocal;

        let mut requested = QosPolicy::default();
        requested.durability = DurabilityKind::Volatile;

        assert!(qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_qos_incompatible_durability() {
        let mut offered = QosPolicy::default();
        offered.durability = DurabilityKind::Volatile;

        let mut requested = QosPolicy::default();
        requested.durability = DurabilityKind::TransientLocal;

        assert!(!qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_qos_incompatible_ownership() {
        let mut offered = QosPolicy::default();
        offered.ownership = OwnershipKind::Shared;

        let mut requested = QosPolicy::default();
        requested.ownership = OwnershipKind::Exclusive;

        assert!(!qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_qos_compatible_partition_overlap() {
        let mut offered = QosPolicy::default();
        offered.partition = Some(vec!["A".to_string(), "B".to_string()]);

        let mut requested = QosPolicy::default();
        requested.partition = Some(vec!["B".to_string(), "C".to_string()]);

        assert!(qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_qos_incompatible_partition_no_overlap() {
        let mut offered = QosPolicy::default();
        offered.partition = Some(vec!["A".to_string()]);

        let mut requested = QosPolicy::default();
        requested.partition = Some(vec!["B".to_string()]);

        assert!(!qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_qos_compatible_one_no_partition() {
        let mut offered = QosPolicy::default();
        offered.partition = Some(vec!["A".to_string()]);

        let requested = QosPolicy::default(); // partition = None

        assert!(qos_compatible(&offered, &requested));
    }

    #[test]
    fn test_serialize_reliability() {
        let qos = QosPolicy::reliable();
        let bytes = serialize_reliability_qos(&qos);
        assert_eq!(bytes[0..4], 2u32.to_le_bytes()); // RELIABLE = 2
    }

    #[test]
    fn test_deserialize_reliability() {
        let qos = QosPolicy::reliable();
        let bytes = serialize_reliability_qos(&qos);
        let (kind, duration) = deserialize_reliability_qos(&bytes).unwrap();
        assert_eq!(kind, ReliabilityKind::Reliable);
        assert_eq!(duration, Duration::ZERO);
    }

    #[test]
    fn test_serialize_durability() {
        let mut qos = QosPolicy::default();
        qos.durability = DurabilityKind::TransientLocal;
        let bytes = serialize_durability_qos(&qos);
        assert_eq!(bytes, 1u32.to_le_bytes());
    }

    #[test]
    fn test_deserialize_durability() {
        let bytes = 2u32.to_le_bytes();
        let kind = deserialize_durability_qos(&bytes).unwrap();
        assert_eq!(kind, DurabilityKind::Transient);
    }

    #[test]
    fn test_builtin_endpoint_qos() {
        let qos = QosPolicy::builtin_endpoint();
        assert_eq!(qos.reliability, ReliabilityKind::Reliable);
        assert_eq!(qos.durability, DurabilityKind::TransientLocal);
        assert_eq!(qos.history, HistoryKind::KeepLast);
        assert_eq!(qos.history_depth, 1);
    }

    #[test]
    fn test_reliability_from_u32() {
        assert_eq!(ReliabilityKind::from_u32(1), Some(ReliabilityKind::BestEffort));
        assert_eq!(ReliabilityKind::from_u32(2), Some(ReliabilityKind::Reliable));
        assert_eq!(ReliabilityKind::from_u32(99), None);
    }

    #[test]
    fn test_durability_from_u32() {
        assert_eq!(DurabilityKind::from_u32(0), Some(DurabilityKind::Volatile));
        assert_eq!(DurabilityKind::from_u32(1), Some(DurabilityKind::TransientLocal));
        assert_eq!(DurabilityKind::from_u32(2), Some(DurabilityKind::Transient));
        assert_eq!(DurabilityKind::from_u32(3), Some(DurabilityKind::Persistent));
        assert_eq!(DurabilityKind::from_u32(99), None);
    }
}
