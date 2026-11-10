import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { VideoWorkspace } from '../video/video-workspace';

@Component({
  selector: 'app-telemetry',
  imports: [RouterLink, VideoWorkspace],
  templateUrl: './telemetry.html',
  styleUrl: './telemetry.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Telemetry {}
