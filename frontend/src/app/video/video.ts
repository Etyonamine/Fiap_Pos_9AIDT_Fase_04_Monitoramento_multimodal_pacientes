import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { VideoWorkspace } from './video-workspace';

@Component({
  selector: 'app-video',
  imports: [RouterLink, VideoWorkspace],
  templateUrl: './video.html',
  styleUrl: './video.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Video {}
