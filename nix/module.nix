{self}: {
  config,
  lib,
  pkgs,
  ...
}: let
  cfg = config.services.chore-stars;
in {
  options.services.chore-stars = {
    enable = lib.mkEnableOption "Chore Stars household board";
    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.system}.default;
    };
    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 8765;
    };
    domain = lib.mkOption {
      type = lib.types.str;
      default = "cs.thompsons.space";
    };
    enableCaddy = lib.mkOption {
      type = lib.types.bool;
      default = true;
    };
    dataDir = lib.mkOption {
      type = lib.types.path;
      default = "/var/lib/chores";
    };
    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Secrets: CHORES_SESSION_SECRET, CHORES_OIDC_CLIENT_SECRET, optional CHORES_NTFY_URL";
    };
    settings = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = {};
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.chores = {
      isSystemUser = true;
      group = "chores";
      home = cfg.dataDir;
    };
    users.groups.chores = {};

    systemd.tmpfiles.rules = [
      "d ${cfg.dataDir} 0750 chores chores -"
      "d ${cfg.dataDir}/photos 0750 chores chores -"
    ];

    services.postgresql = {
      enable = true;
      ensureDatabases = ["chores"];
      ensureUsers = [
        {
          name = "chores";
          ensureDBOwnership = true;
        }
      ];
    };

    systemd.services.chore-stars = {
      description = "Chore Stars";
      after = ["network.target" "postgresql.service"];
      wants = ["postgresql.service"];
      wantedBy = ["multi-user.target"];
      environment =
        {
          CHORES_DATABASE_URL = "postgresql+psycopg2:///chores?host=/run/postgresql";
          CHORES_PHOTO_DIR = "${cfg.dataDir}/photos";
          CHORES_HOST = cfg.host;
          CHORES_PORT = toString cfg.port;
          CHORES_BASE_URL = "https://${cfg.domain}";
          CHORES_TIMEZONE = "America/Indiana/Indianapolis";
          CHORES_OIDC_ISSUER = "https://id.thompsons.space";
        }
        // cfg.settings;
      serviceConfig =
        {
          User = "chores";
          Group = "chores";
          ExecStart = "${cfg.package}/bin/chore-stars serve";
          Restart = "on-failure";
          WorkingDirectory = cfg.dataDir;
          StateDirectory = "chores";
        }
        // lib.optionalAttrs (cfg.environmentFile != null) {
          EnvironmentFile = cfg.environmentFile;
        };
    };

    systemd.services.chore-stars-jobs = {
      description = "Chore Stars daily jobs";
      after = ["chore-stars.service" "postgresql.service"];
      environment = config.systemd.services.chore-stars.environment;
      serviceConfig =
        {
          User = "chores";
          Group = "chores";
          Type = "oneshot";
          ExecStart = "${cfg.package}/bin/chore-stars job daily";
          WorkingDirectory = cfg.dataDir;
        }
        // lib.optionalAttrs (cfg.environmentFile != null) {
          EnvironmentFile = cfg.environmentFile;
        };
    };

    systemd.timers.chore-stars-jobs = {
      wantedBy = ["timers.target"];
      timerConfig = {
        OnCalendar = "*:0/5";
        Persistent = true;
      };
    };

    services.caddy = lib.mkIf cfg.enableCaddy {
      enable = true;
      virtualHosts.${cfg.domain}.extraConfig = ''
        reverse_proxy ${cfg.host}:${toString cfg.port}
      '';
    };
  };
}
