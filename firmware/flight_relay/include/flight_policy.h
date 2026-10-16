#pragma once
#include <cmath>
#include <cstdint>
#include <cstring>

namespace vanni {
constexpr float kAltitudeM = 1.0f;
constexpr float kSpeedMs = 0.5f;
constexpr double kRadiusM = 20.0;
constexpr uint32_t kMissionMs = 120000;
constexpr uint32_t kEnableMs = 120000;
inline bool fresh(uint32_t now, uint32_t stamp, uint32_t limit = 3000) {
    return stamp != 0 && uint32_t(now - stamp) <= limit;
}
inline double distance(double a, double b, double c, double d) {
    constexpr double rad = 3.141592653589793 / 180.;
    const double x = std::sin((c-a)*rad/2), y = std::sin((d-b)*rad/2);
    const double h = x*x + std::cos(a*rad)*std::cos(c*rad)*y*y;
    return 12742000. * std::asin(std::sqrt(h > 1 ? 1 : h));
}
struct Telemetry {
    uint32_t heartbeat=0, position=0, gps=0, radio=0, power=0, system=0;
    uint32_t home=0, extended=0, estimator=0, params=0;
    double lat=0, lon=0, homeLat=0, homeLon=0;
    float altitude=0, voltage=0, navSpeed=0, climbSpeed=0, descendSpeed=0;
    float landSpeed=0;
    int batteryPct=-1, gpsFix=0, satellites=0, mode=0;
    bool armed=false, rcOk=false, landed=false, prearmOk=false, ekfOk=false;
    bool critical=false, linkFailsafeConfigured=false;
};
struct Command {
    char id[64] = {};
    double lat=0, lon=0, created=0, expires=0;
    bool verifiedVoice=false;
};
inline const char* preflight(const Telemetry& t, uint32_t now, int cells) {
    if (!fresh(now,t.heartbeat)) return "Pixhawk heartbeat missing/stale";
    if (t.armed) return "aircraft already armed";
    if (!fresh(now,t.extended,5000) || !t.landed) return "grounded state unconfirmed";
    if (!fresh(now,t.position) || !fresh(now,t.gps) || t.gpsFix<3 || t.satellites<8)
        return "fresh 3D GPS with 8 satellites required";
    if (!std::isfinite(t.lat) || !std::isfinite(t.lon) || (t.lat==0 && t.lon==0))
        return "invalid aircraft coordinates";
    if (!fresh(now,t.home,10000) || distance(t.lat,t.lon,t.homeLat,t.homeLon)>5)
        return "fresh launch home must be within 5m";
    if (!fresh(now,t.radio) || !t.rcOk) return "RC input missing/stale";
    if (cells<2 || cells>6) return "battery cell count not provisioned";
    if (!fresh(now,t.power) || !std::isfinite(t.voltage) ||
        t.voltage<cells*3.7f || t.voltage>cells*4.25f)
        return "battery voltage missing, low or implausible";
    if (t.batteryPct<30) return "battery percentage missing/below 30";
    if (!fresh(now,t.system) || !t.prearmOk || t.critical)
        return "Pixhawk pre-arm health/failsafe blocks dispatch";
    if (!fresh(now,t.estimator) || !t.ekfOk) return "EKF position/attitude unhealthy";
    if (!fresh(now,t.params,15000)) return "flight limit parameters unavailable";
    if (t.navSpeed<=0 || t.navSpeed>.501f || t.climbSpeed<=0 || t.climbSpeed>.501f ||
        t.descendSpeed<=0 || t.descendSpeed>.501f || t.landSpeed<=0 || t.landSpeed>.501f)
        return "Pixhawk speed limits must be at most 0.5m/s";
    if (!t.linkFailsafeConfigured) return "Pixhawk companion link-loss failsafe unverified";
    return nullptr;
}
enum class State { Idle, Guided, Speed, Arm, Takeoff, Outbound, Return,
                   Landing, AbortLanding, Pilot, Completed, Failed };
enum class Kind { None, Guided, Speed, Arm, Takeoff, Waypoint, Land };
struct Action { Kind kind=Kind::None; double lat=0, lon=0; float altitude=kAltitudeM; };
class Controller {
public:
    State state=State::Idle;
    const char* detail="flight locked";
    Command command{};
    double launchLat=0, launchLon=0;
    uint32_t started=0, phase=0, lastAction=0, unlockedAt=0;
    bool enabled=false, continuous=false, acceptedAck=false, sawArmed=false;
    bool recoveryRequired=false, hadAirborne=false;
    int cells=0;
    bool busy() const { return state!=State::Idle && state!=State::Completed && state!=State::Failed; }
    bool terminal() const { return state==State::Completed || state==State::Failed; }
    bool unlocked(uint32_t now) const {
        return enabled && (continuous || uint32_t(now-unlockedAt)<kEnableMs) && !recoveryRequired;
    }
    const char* accept(const Command& c,const Telemetry& t,uint32_t now,double utc,bool duplicate) {
        if (busy()) return "mission busy";
        if (!unlocked(now)) return "local flight authorization absent/expired";
        if (duplicate) return "duplicate command";
        if (!c.verifiedVoice || c.id[0]==0) return "only approved verified voice commands allowed";
        if (!std::isfinite(c.created) || !std::isfinite(c.expires) || utc<1700000000 ||
            c.created>utc+2 || c.expires<=utc || c.expires-c.created>60.01 || c.expires<=c.created)
            return "command expired or clock/expiry invalid";
        if (!std::isfinite(c.lat) || !std::isfinite(c.lon) || c.lat < -90 || c.lat > 90 ||
            c.lon < -180 || c.lon > 180 || (c.lat==0 && c.lon==0)) return "invalid coordinates";
        if (const char* why=preflight(t,now,cells)) return why;
        if (distance(t.lat,t.lon,c.lat,c.lon)>kRadiusM) return "target beyond 20m prototype radius";
        command=c; launchLat=t.lat; launchLon=t.lon; started=now;
        if(!continuous)enabled=false;
        sawArmed=false; hadAirborne=false; detail="mission accepted"; enter(State::Guided,now);
        return nullptr;
    }
    void confirm(bool ok,uint32_t now) {
        if (!ok) { abort("Pixhawk rejected command",now); return; }
        acceptedAck=true;
    }
    void abort(const char* why,uint32_t now) {
        detail=why; enter(sawArmed ? State::AbortLanding : State::Failed,now);
    }
    Action tick(const Telemetry& t,uint32_t now) {
        if (!busy()) return {};
        sawArmed=sawArmed||t.armed;
        hadAirborne=hadAirborne||(!t.landed && fresh(now,t.extended,5000));
        if (state==State::Pilot) {
            if (fresh(now,t.heartbeat) && !t.armed && t.landed && fresh(now,t.extended,5000))
                enter(State::Failed,now);
            return {};
        }
        if (sawArmed && !t.armed && fresh(now,t.heartbeat)) {
            if (t.landed && fresh(now,t.extended,5000)) {
                if (state==State::Landing && hadAirborne) {detail="landed and disarmed";enter(State::Completed,now);}
                else {detail="disarmed before mission completion";enter(State::Failed,now);}
            }
            return {};
        }
        // Flight-controller failsafes and the RC pilot own unexpected modes.
        if (sawArmed && fresh(now,t.heartbeat) && t.mode!=4 &&
            !(state==State::Landing && t.mode==9) && !(state==State::AbortLanding && t.mode==9)) {
            detail="pilot or Pixhawk failsafe took control"; enter(State::Pilot,now); return {};
        }
        if (!fresh(now,t.heartbeat)) {detail="MAVLink lost; Pixhawk onboard failsafe owns recovery";return {};}
        if (state!=State::Landing && state!=State::AbortLanding) {
            if (uint32_t(now-started)>kMissionMs) abort("mission timeout",now);
            else if (!fresh(now,t.position) || !fresh(now,t.gps) || t.gpsFix<3 || t.satellites<8 ||
                     !fresh(now,t.estimator) || !t.ekfOk) abort("GPS/EKF lost",now);
            else if (!fresh(now,t.power) || t.voltage<cells*3.5f || t.critical)
                abort("low battery or Pixhawk failsafe",now);
            else if (!fresh(now,t.radio) || !t.rcOk) abort("RC input lost",now);
        }
        if (!busy()) return {};
        if (state==State::Guided && t.mode==4) enter(State::Speed,now);
        if (state==State::Speed && acceptedAck) enter(State::Arm,now);
        if (state==State::Arm && t.armed && acceptedAck) enter(State::Takeoff,now);
        if (state==State::Takeoff && acceptedAck && t.altitude>=.8f && !t.landed && fresh(now,t.extended,5000))
            enter(State::Outbound,now);
        if (state==State::Outbound && fresh(now,t.position) && t.altitude>=.7f &&
            distance(t.lat,t.lon,command.lat,command.lon)<=1.5) enter(State::Return,now);
        if (state==State::Return && fresh(now,t.position) &&
            distance(t.lat,t.lon,launchLat,launchLon)<=1.5) enter(State::Landing,now);
        if (state!=State::Outbound && state!=State::Return && state!=State::Landing &&
            state!=State::AbortLanding && uint32_t(now-phase)>15000) abort("command/phase confirmation timeout",now);
        if ((state==State::Landing || state==State::AbortLanding) && t.mode==9) return {};
        if (uint32_t(now-lastAction)<1000) return {};
        lastAction=now;
        switch(state) {
        case State::Guided:return {Kind::Guided};
        case State::Speed:return {Kind::Speed};
        case State::Arm:return {Kind::Arm};
        case State::Takeoff:return acceptedAck ? Action{} : Action{Kind::Takeoff};
        case State::Outbound:return {Kind::Waypoint,command.lat,command.lon};
        case State::Return:return {Kind::Waypoint,launchLat,launchLon};
        case State::Landing:case State::AbortLanding:return {Kind::Land};
        default:return {};
        }
    }
    void enter(State next,uint32_t now) {state=next;phase=now;lastAction=now-1000;acceptedAck=false;}
};
}
