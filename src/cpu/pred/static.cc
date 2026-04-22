#include "cpu/pred/static.hh"

#include "base/intmath.hh"
#include "base/logging.hh"
#include "base/trace.hh"
#include "debug/Fetch.hh"

namespace gem5
{

namespace branch_prediction
{

StaticBP::StaticBP(const StaticBPParams &params)
    : ConditionalPredictor(params),
      staticPredictionAlwaysTaken(params.staticPredictionAlwaysTaken)
{}

bool
StaticBP::lookup(ThreadID tid, Addr branch_addr, void *&bp_history)
{
    bool taken = staticPredictionAlwaysTaken;
    return taken;
}

void
StaticBP::update(ThreadID tid, Addr pc, bool taken, void *&bp_history,
                 bool squashed, const StaticInstPtr &inst, Addr target)
{}

StaticIndirectBP::StaticIndirectBP(const StaticIndirectBPParams &params)
    : IndirectPredictor(params)
{}

} // namespace branch_prediction
} // namespace gem5
