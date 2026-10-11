import Foundation

/// Fetch the static feed on open, keep the last good copy, and decide
/// Live now / Starting soon on device. Mirrors `homecircle_feed.live`.
public struct MeetingFeedFile: Decodable {
    public let schemaVersion: String
    public let country: String
    public let generatedAt: String
    public let meetingCount: Int
    public let meetings: [Meeting]
}

public struct Meeting: Decodable, Identifiable {
    public let id: String
    public let fellowship: String
    public let name: String
    public let schedule: Schedule
    public let format: String
    public let location: MeetingLocation
    public let online: OnlineAccess
    public let tags: [String]
    public let notes: String?
    public let source: MeetingSource
}

public struct Schedule: Decodable {
    public let day: String
    public let weekday: Int
    public let start: String
    public let timezone: String
    public let timezoneSource: String
    public let durationMinutes: Int
}

public struct MeetingLocation: Decodable {
    public let name: String?
    public let address: String?
    public let suburb: String?
    public let state: String?
    public let postalCode: String?
    public let country: String
    public let latitude: Double?
    public let longitude: Double?
    public let approximate: Bool
}

public struct OnlineAccess: Decodable {
    public let url: String?
    public let phone: String?
}

public struct MeetingSource: Decodable {
    public let id: String
    public let name: String
    public let url: String
    public let recordUrl: String?
    public let lastSeen: String
}

public enum FeedOrigin {
    case network
    case cache
}

public enum FeedClientError: Error {
    case unavailable
}

public struct FeedClient {
    public let feedURL: URL
    public let cacheURL: URL
    public var soonWindowMinutes: Int = 30

    public init(feedURL: URL, cacheURL: URL) {
        self.feedURL = feedURL
        self.cacheURL = cacheURL
    }

    /// Network first. The previous file is used when the phone is offline.
    public func load(session: URLSession = .shared) async throws -> (MeetingFeedFile, FeedOrigin) {
        var request = URLRequest(url: feedURL)
        request.setValue("HomeCircle/1.0", forHTTPHeaderField: "User-Agent")
        request.timeoutInterval = 20
        do {
            let (data, response) = try await session.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200 ..< 300).contains(status) else { throw URLError(.badServerResponse) }
            try data.write(to: cacheURL, options: .atomic)
            return (try Self.decode(data), .network)
        } catch {
            guard let data = try? Data(contentsOf: cacheURL) else { throw FeedClientError.unavailable }
            return (try Self.decode(data), .cache)
        }
    }

    public func liveNow(_ meetings: [Meeting], now: Date = Date()) -> [Meeting] {
        meetings.filter { isLive($0, now: now) }
    }

    public func startingSoon(_ meetings: [Meeting], now: Date = Date()) -> [Meeting] {
        meetings.filter { startsSoon($0, now: now) }
    }

    public func isLive(_ meeting: Meeting, now: Date = Date()) -> Bool {
        let start = inProgressStart(meeting, now: now)
        let end = start.addingTimeInterval(TimeInterval(meeting.schedule.durationMinutes * 60))
        return start <= now && now < end
    }

    public func startsSoon(_ meeting: Meeting, now: Date = Date()) -> Bool {
        if isLive(meeting, now: now) { return false }
        let start = nextStart(meeting, now: now)
        let delta = start.timeIntervalSince(now)
        return delta > 0 && delta <= Double(soonWindowMinutes * 60)
    }

    private static func decode(_ data: Data) throws -> MeetingFeedFile {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(MeetingFeedFile.self, from: data)
    }

    /// Most recent scheduled start at or before `now`.
    private func inProgressStart(_ meeting: Meeting, now: Date) -> Date {
        let calendar = meetingCalendar(meeting)
        let hourMinute = clock(meeting.schedule.start)
        let localWeekday = calendar.component(.weekday, from: now) - 1
        let daysBack = (localWeekday - meeting.schedule.weekday + 7) % 7
        var parts = calendar.dateComponents([.year, .month, .day], from: now)
        parts.hour = hourMinute.0
        parts.minute = hourMinute.1
        parts.second = 0
        let todayAtStart = calendar.date(from: parts) ?? now
        let start = calendar.date(byAdding: .day, value: -daysBack, to: todayAtStart) ?? todayAtStart
        if start > now {
            return calendar.date(byAdding: .day, value: -7, to: start) ?? start
        }
        return start
    }

    private func nextStart(_ meeting: Meeting, now: Date) -> Date {
        let previous = inProgressStart(meeting, now: now)
        return meetingCalendar(meeting).date(byAdding: .day, value: 7, to: previous) ?? previous
    }

    private func meetingCalendar(_ meeting: Meeting) -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: meeting.schedule.timezone) ?? TimeZone(secondsFromGMT: 10 * 3600)!
        return calendar
    }

    private func clock(_ value: String) -> (Int, Int) {
        let parts = value.split(separator: ":")
        return (Int(parts.first ?? "0") ?? 0, Int(parts.dropFirst().first ?? "0") ?? 0)
    }
}
