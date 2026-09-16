<template>
  <q-page class="q-pa-md">
    <!-- Header Controls -->
    <div class="row justify-between items-center q-mb-md">
      <div class="text-h5 text-weight-bold">Execution Telemetry</div>
      <div>
        <q-btn
          color="primary"
          icon="refresh"
          label="Refresh"
          dense
          class="q-px-sm"
          :loading="loading"
          @click="loadData"
        />
      </div>
    </div>

    <!-- Warnings & Alerts -->
    <div v-if="telemetry" class="q-gutter-y-sm q-mb-md">
      <q-banner
        v-if="telemetry.unhit_teams && telemetry.unhit_teams.length > 0"
        dense
        rounded
        class="bg-warning text-dark"
      >
        <template v-slot:avatar>
          <q-icon name="warning" color="dark" />
        </template>
        <div class="text-weight-bold">
          Missing targets! The following {{ telemetry.unhit_teams.length }} teams have not been hit:
        </div>
        <div class="q-mt-xs">
          <q-chip
            v-for="team in telemetry.unhit_teams"
            :key="team"
            size="sm"
            color="grey-9"
            text-color="white"
          >
            {{ team }}
          </q-chip>
        </div>
      </q-banner>

      <q-banner
        v-if="telemetry.regressions && telemetry.regressions.length > 0"
        dense
        rounded
        class="bg-negative text-white"
      >
        <template v-slot:avatar>
          <q-icon name="report_problem" color="white" />
        </template>
        <div class="text-weight-bold">Sudden Regressions Detected:</div>
        <div
          v-for="(reg, idx) in telemetry.regressions"
          :key="idx"
          class="text-caption q-mt-xs"
        >
          • <strong>{{ reg.sploit_id }}</strong>: {{ reg.reason }}
        </div>
      </q-banner>
    </div>

    <!-- Sploits Section -->
    <div class="q-mb-lg">
      <div class="text-h6 q-mb-sm">Sploits Overview</div>
      <q-table
        dense
        :rows="sploits"
        :columns="sploitColumns"
        :rows-per-page-options="[10, 25, 0]"
        row-key="sploit_id"
        table-header-class="bg-cbs text-cbs"
        no-data-label="No telemetry data recorded yet"
      >
        <template v-slot:body-cell-status="props">
          <q-td :props="props">
            <q-badge
              v-if="props.row.regression"
              color="negative"
              label="REGRESSED"
            />
            <q-badge
              v-else-if="props.row.success_rate >= 75"
              color="positive"
              label="HEALTHY"
            />
            <q-badge
              v-else-if="props.row.success_rate > 0"
              color="warning"
              label="DEGRADED"
            />
            <q-badge v-else color="grey" label="FAILING" />
          </q-td>
        </template>
        <template v-slot:body-cell-success_rate="props">
          <q-td :props="props">
            <span
              :class="{
                'text-positive': props.value >= 75,
                'text-warning': props.value > 0 && props.value < 75,
                'text-negative': props.value === 0,
              }"
            >
              {{ props.value }}%
            </span>
          </q-td>
        </template>
        <template v-slot:body-cell-last_success="props">
          <q-td :props="props">
            {{ formatTime(props.value) }}
          </q-td>
        </template>
      </q-table>
    </div>

    <!-- Teams Telemetry Section -->
    <div class="q-mb-lg">
      <div class="text-h6 q-mb-sm">Teams Attack Status</div>
      <q-table
        dense
        :rows="teams"
        :columns="teamColumns"
        :rows-per-page-options="[15, 30, 0]"
        row-key="team"
        table-header-class="bg-cbs text-cbs"
        no-data-label="No teams"
      >
        <template v-slot:body-cell-status="props">
          <q-td :props="props">
            <q-badge
              v-if="props.value === 'unhit'"
              color="negative"
              label="UNHIT"
            />
            <q-badge
              v-else-if="props.value === 'ok'"
              color="positive"
              label="ACTIVE"
            />
            <q-badge v-else color="warning" label="FAILING" />
          </q-td>
        </template>
        <template v-slot:body-cell-success_rate="props">
          <q-td :props="props">
            <span>{{ props.value }}%</span>
          </q-td>
        </template>
        <template v-slot:body-cell-last_run="props">
          <q-td :props="props">
            {{ formatTime(props.value) }}
          </q-td>
        </template>
        <template v-slot:body-cell-last_success="props">
          <q-td :props="props">
            {{ formatTime(props.value) }}
          </q-td>
        </template>
      </q-table>
    </div>

    <!-- Recent Executions Log -->
    <div class="q-mb-lg">
      <div class="text-h6 q-mb-sm">Recent Executions Log</div>
      <q-table
        dense
        :rows="recentExecutions"
        :columns="executionColumns"
        :rows-per-page-options="[15, 30, 50]"
        row-key="id"
        table-header-class="bg-cbs text-cbs"
        no-data-label="No execution records"
      >
        <template v-slot:body-cell-exit="props">
          <q-td :props="props">
            <q-badge
              v-if="props.row.timeout"
              color="negative"
              label="TIMEOUT"
            />
            <q-badge
              v-else-if="props.row.exit_code === 0"
              color="positive"
              label="EXIT 0"
            />
            <q-badge
              v-else
              color="negative"
              :label="'EXIT ' + props.row.exit_code"
            />
          </q-td>
        </template>
        <template v-slot:body-cell-start_time="props">
          <q-td :props="props">
            {{ formatTime(props.value) }}
          </q-td>
        </template>
        <template v-slot:body-cell-actions="props">
          <q-td :props="props">
            <q-btn
              v-if="props.row.output_preview"
              size="sm"
              flat
              dense
              icon="visibility"
              label="Output"
              @click="openOutputDialog(props.row)"
            />
          </q-td>
        </template>
      </q-table>
    </div>

    <!-- Output Preview Dialog -->
    <q-dialog v-model="dialogOpen">
      <q-card style="min-width: 600px; max-width: 80vw">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">
            {{ selectedExecution?.sploit_id }} → {{ selectedExecution?.team }} (Round {{ selectedExecution?.round }})
          </div>
          <q-space />
          <q-btn icon="close" flat round dense v-close-popup />
        </q-card-section>
        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-sm">
            Exit Code: {{ selectedExecution?.exit_code }} | Timeout: {{ selectedExecution?.timeout }} | Duration: {{ selectedExecution?.duration }}s
          </div>
          <pre
            class="bg-grey-10 text-grey-2 q-pa-sm rounded-borders"
            style="max-height: 400px; overflow-y: auto; white-space: pre-wrap; font-size: 12px;"
          >{{ selectedExecution?.output_preview || 'No output recorded' }}</pre>
        </q-card-section>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script>
import { mapState, mapActions } from "vuex";
import moment from "moment";

export default {
  name: "Telemetry",
  data() {
    return {
      loading: false,
      dialogOpen: false,
      selectedExecution: null,
      pollInterval: null,
      sploitColumns: [
        { name: "sploit_id", label: "Sploit", field: "sploit_id", align: "left" },
        { name: "service", label: "Service", field: "service", align: "center" },
        { name: "status", label: "Health", align: "center" },
        { name: "total_runs", label: "Runs", field: "total_runs", align: "center" },
        { name: "success_rate", label: "Success %", field: "success_rate", align: "center" },
        { name: "timeout_rate", label: "Timeout %", field: "timeout_rate", align: "center" },
        { name: "flags_found", label: "Flags", field: "flags_found", align: "center" },
        { name: "flags_per_run", label: "Flags/Run", field: "flags_per_run", align: "center" },
        { name: "p50_duration", label: "p50 (s)", field: "p50_duration", align: "center" },
        { name: "p95_duration", label: "p95 (s)", field: "p95_duration", align: "center" },
        { name: "last_success", label: "Last Success", field: "last_success", align: "center" },
      ],
      teamColumns: [
        { name: "team", label: "Team", field: "team", align: "left" },
        { name: "address", label: "Address", field: "address", align: "center" },
        { name: "status", label: "Status", field: "status", align: "center" },
        { name: "total_runs", label: "Runs", field: "total_runs", align: "center" },
        { name: "success_rate", label: "Success %", field: "success_rate", align: "center" },
        { name: "timeout_runs", label: "Timeouts", field: "timeout_runs", align: "center" },
        { name: "flags_found", label: "Flags", field: "flags_found", align: "center" },
        { name: "flags_per_run", label: "Flags/Run", field: "flags_per_run", align: "center" },
        { name: "p50_duration", label: "p50 (s)", field: "p50_duration", align: "center" },
        { name: "p95_duration", label: "p95 (s)", field: "p95_duration", align: "center" },
        { name: "last_run", label: "Last Hit", field: "last_run", align: "center" },
        { name: "last_success", label: "Last Success", field: "last_success", align: "center" },
      ],
      executionColumns: [
        { name: "id", label: "ID", field: "id", align: "center" },
        { name: "sploit_id", label: "Sploit", field: "sploit_id", align: "left" },
        { name: "service", label: "Service", field: "service", align: "center" },
        { name: "team", label: "Team", field: "team", align: "left" },
        { name: "round", label: "Round", field: "round", align: "center" },
        { name: "duration", label: "Duration", field: (row) => row.duration + "s", align: "center" },
        { name: "exit", label: "Exit", align: "center" },
        { name: "flags_found", label: "Flags", field: "flags_found", align: "center" },
        { name: "start_time", label: "Time", field: "start_time", align: "center" },
        { name: "actions", label: "Details", align: "center" },
      ],
    };
  },
  computed: {
    ...mapState(["telemetry"]),
    sploits() {
      return this.telemetry?.sploits || [];
    },
    teams() {
      return this.telemetry?.teams || [];
    },
    recentExecutions() {
      return this.telemetry?.recent_executions || [];
    },
  },
  methods: {
    ...mapActions(["fetchTelemetry"]),
    async loadData() {
      this.loading = true;
      await this.fetchTelemetry();
      this.loading = false;
    },
    formatTime(val) {
      if (!val) return "Never";
      return moment.unix(val).format("HH:mm:ss");
    },
    openOutputDialog(execution) {
      this.selectedExecution = execution;
      this.dialogOpen = true;
    },
  },
  async created() {
    await this.loadData();
    this.pollInterval = setInterval(this.loadData, 5000);
  },
  beforeUnmount() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
    }
  },
};
</script>
