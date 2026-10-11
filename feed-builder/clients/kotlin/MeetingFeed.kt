package app.homecircle.meetings

import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * Fetch the static feed on open, keep the last good copy, and decide
 * Live now / Starting soon on device. Mirrors `homecircle_feed.live`.
 * Android provides org.json and java.time.
 */
data class Meeting(
    val id: String,
    val fellowship: String,
    val name: String,
    val weekday: Int,
    val start: String,
    val timezone: String,
    val durationMinutes: Int,
    val format: String,
)

enum class FeedOrigin { NETWORK, CACHE }

class FeedUnavailable : Exception("Meeting feed is unreachable and no cache is stored.")

class MeetingFeedClient(
    private val feedUrl: String,
    private val cacheFile: File,
    private val soonWindowMinutes: Long = 30,
) {
    fun load(): Pair<List<Meeting>, FeedOrigin> {
        try {
            val body = httpGet(feedUrl)
            cacheFile.parentFile?.mkdirs()
            cacheFile.writeText(body)
            return parse(body) to FeedOrigin.NETWORK
        } catch (error: Exception) {
            if (!cacheFile.exists()) throw FeedUnavailable()
            return parse(cacheFile.readText()) to FeedOrigin.CACHE
        }
    }

    fun liveNow(meetings: List<Meeting>, now: Instant = Instant.now()): List<Meeting> =
        meetings.filter { isLive(it, now) }

    fun startingSoon(meetings: List<Meeting>, now: Instant = Instant.now()): List<Meeting> =
        meetings.filter { startsSoon(it, now) }

    fun isLive(meeting: Meeting, now: Instant = Instant.now()): Boolean {
        val start = inProgressStart(meeting, now)
        val end = start.plusMinutes(meeting.durationMinutes.toLong())
        val localNow = now.atZone(start.zone)
        return !localNow.isBefore(start) && localNow.isBefore(end)
    }

    fun startsSoon(meeting: Meeting, now: Instant = Instant.now()): Boolean {
        if (isLive(meeting, now)) return false
        val start = inProgressStart(meeting, now).plusDays(7)
        val localNow = now.atZone(start.zone)
        val seconds = java.time.Duration.between(localNow, start).seconds
        return seconds in 1..(soonWindowMinutes * 60)
    }

    /** Most recent scheduled start at or before [now], in the meeting zone. */
    fun inProgressStart(meeting: Meeting, now: Instant): ZonedDateTime {
        val zone = ZoneId.of(meeting.timezone)
        val localNow = now.atZone(zone)
        val parts = meeting.start.split(":")
        val localWeekday = localNow.dayOfWeek.value % 7 // Sunday=0 … Saturday=6
        val daysBack = Math.floorMod(localWeekday - meeting.weekday, 7)
        var start = localNow
            .withHour(parts[0].toInt())
            .withMinute(parts[1].toInt())
            .withSecond(0)
            .withNano(0)
            .minusDays(daysBack.toLong())
        if (start.toInstant().isAfter(now)) {
            start = start.minusDays(7)
        }
        return start
    }

    private fun httpGet(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.requestMethod = "GET"
        connection.setRequestProperty("User-Agent", "HomeCircle/1.0")
        connection.connectTimeout = 20_000
        connection.readTimeout = 20_000
        connection.inputStream.bufferedReader().use { reader ->
            val code = connection.responseCode
            if (code !in 200..299) error("HTTP $code")
            return reader.readText()
        }
    }

    private fun parse(body: String): List<Meeting> {
        val array = JSONObject(body).getJSONArray("meetings")
        return (0 until array.length()).map { index ->
            val item = array.getJSONObject(index)
            val schedule = item.getJSONObject("schedule")
            Meeting(
                id = item.getString("id"),
                fellowship = item.getString("fellowship"),
                name = item.getString("name"),
                weekday = schedule.getInt("weekday"),
                start = schedule.getString("start"),
                timezone = schedule.getString("timezone"),
                durationMinutes = schedule.getInt("duration_minutes"),
                format = item.getString("format"),
            )
        }
    }
}
